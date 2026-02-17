#!/usr/bin/env python3
"""
upload_to_wiki.py - Bulk upload converted pages to MediaWiki

Uses mwclient to upload pages via the MediaWiki API.
Handles page creation, category assignment, and redirects.

Usage:
    python upload_to_wiki.py --wiki-url https://wiki.dreamfactory.com \
                              --input-dir ./converted \
                              --inventory migration_inventory.csv \
                              [--dry-run] [--username USER] [--password PASS]
"""

import os
import re
import csv
import argparse
import getpass
from pathlib import Path
from typing import Dict, List, Optional

try:
    import mwclient
except ImportError:
    print("Error: mwclient not installed. Run: pip install mwclient")
    exit(1)


class WikiUploader:
    """Handles uploading content to MediaWiki."""

    def __init__(self, wiki_url: str, username: str = None, password: str = None,
                 dry_run: bool = False):
        self.wiki_url = wiki_url
        self.dry_run = dry_run
        self.site = None
        self.username = username
        self.password = password
        self.stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0
        }

    def connect(self) -> bool:
        """Connect to the MediaWiki site."""
        try:
            # Parse URL to get host
            url = self.wiki_url.replace('https://', '').replace('http://', '')
            host = url.split('/')[0]
            path = '/' + '/'.join(url.split('/')[1:]) if '/' in url else '/'

            if not path.endswith('/'):
                path += '/'

            print(f"Connecting to {host}{path}...")

            if self.dry_run:
                print("  [DRY RUN - No actual connection]")
                return True

            scheme = 'https' if self.wiki_url.startswith('https://') else 'http'
            self.site = mwclient.Site(host, path=path, scheme=scheme)

            if self.username and self.password:
                self.site.login(self.username, self.password)
                print(f"  Logged in as: {self.username}")
            else:
                print("  Anonymous connection (limited permissions)")

            return True

        except Exception as e:
            print(f"Error connecting to wiki: {e}")
            return False

    def upload_page(self, page_name: str, content: str, summary: str = None) -> bool:
        """
        Upload a single page to the wiki.

        Args:
            page_name: The wiki page title
            content: The page content (MediaWiki syntax)
            summary: Edit summary

        Returns:
            True if successful, False otherwise
        """
        if not summary:
            summary = "Documentation migration from Docusaurus/Hugo"

        try:
            print(f"  Uploading: {page_name}...", end=' ')

            if self.dry_run:
                print("[DRY RUN - Would upload]")
                self.stats['created'] += 1
                return True

            page = self.site.pages[page_name]

            if page.exists:
                # Page exists - update it
                page.save(content, summary=summary + " (update)")
                print("Updated")
                self.stats['updated'] += 1
            else:
                # New page
                page.save(content, summary=summary + " (new)")
                print("Created")
                self.stats['created'] += 1

            return True

        except mwclient.errors.ProtectedPageError:
            print("FAILED (protected page)")
            self.stats['failed'] += 1
            return False
        except Exception as e:
            print(f"FAILED ({e})")
            self.stats['failed'] += 1
            return False

    def create_redirect(self, from_page: str, to_page: str) -> bool:
        """Create a redirect from one page to another."""
        content = f"#REDIRECT [[{to_page}]]"
        return self.upload_page(from_page, content, "Creating redirect")

    def upload_image(self, image_path: str, description: str = None) -> bool:
        """Upload an image file to the wiki."""
        try:
            filename = Path(image_path).name
            print(f"  Uploading image: {filename}...", end=' ')

            if self.dry_run:
                print("[DRY RUN - Would upload]")
                return True

            with open(image_path, 'rb') as f:
                self.site.upload(
                    f,
                    filename=filename,
                    description=description or "Documentation image",
                    ignore=True  # Ignore warnings about duplicate files
                )

            print("Uploaded")
            return True

        except Exception as e:
            print(f"FAILED ({e})")
            return False

    def upload_directory(self, input_dir: str, inventory_file: str = None) -> Dict:
        """
        Upload all wiki files from a directory.

        Args:
            input_dir: Directory containing .wiki files
            inventory_file: Optional CSV inventory for page name mappings

        Returns:
            Statistics dictionary
        """
        input_path = Path(input_dir)

        if not input_path.exists():
            print(f"Error: Input directory not found: {input_dir}")
            return self.stats

        # Load inventory for page name mappings if provided
        page_mappings = {}
        if inventory_file and Path(inventory_file).exists():
            with open(inventory_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    source = row.get('source_path', '')
                    target = row.get('target_wiki_page', '')
                    if source and target:
                        # Create mapping from converted filename to wiki page name
                        wiki_file = source.replace('.md', '.wiki')
                        page_mappings[wiki_file] = target

        # Find all .wiki files
        wiki_files = list(input_path.rglob('*.wiki'))
        print(f"\nFound {len(wiki_files)} wiki files to upload\n")

        for wiki_file in wiki_files:
            rel_path = wiki_file.relative_to(input_path)

            # Determine page name
            # First check inventory mapping
            page_name = None
            for source, target in page_mappings.items():
                if str(rel_path) in source or source in str(rel_path):
                    page_name = target
                    break

            # Fall back to filename-based page name
            if not page_name:
                page_name = str(rel_path.with_suffix('')).replace('/', '/')
                page_name = '_'.join(
                    word.capitalize()
                    for word in page_name.replace('-', '_').split('_')
                )

            # Read content
            try:
                content = wiki_file.read_text(encoding='utf-8')
                self.upload_page(page_name, content)
            except Exception as e:
                print(f"  Error reading {wiki_file}: {e}")
                self.stats['failed'] += 1

        return self.stats

    def print_stats(self):
        """Print upload statistics."""
        print("\n" + "=" * 50)
        print("Upload Statistics")
        print("=" * 50)
        print(f"  Created: {self.stats['created']}")
        print(f"  Updated: {self.stats['updated']}")
        print(f"  Skipped: {self.stats['skipped']}")
        print(f"  Failed:  {self.stats['failed']}")
        total = sum(self.stats.values())
        success = self.stats['created'] + self.stats['updated']
        print(f"  Success rate: {success}/{total} ({100*success/max(total,1):.1f}%)")
        print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description='Upload converted documentation to MediaWiki'
    )
    parser.add_argument('--wiki-url', '-w', required=True,
                        help='MediaWiki URL (e.g., https://wiki.dreamfactory.com)')
    parser.add_argument('--input-dir', '-i', default='./converted',
                        help='Directory containing .wiki files')
    parser.add_argument('--inventory', '-c',
                        help='Migration inventory CSV for page name mappings')
    parser.add_argument('--username', '-u',
                        help='MediaWiki username')
    parser.add_argument('--password', '-p',
                        help='MediaWiki password (or use WIKI_PASSWORD env var)')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Simulate upload without making changes')
    parser.add_argument('--single-page', '-s',
                        help='Upload a single .wiki file')

    args = parser.parse_args()

    # Get password from environment if not provided
    password = args.password or os.environ.get('WIKI_PASSWORD')
    if args.username and not password and not args.dry_run:
        password = getpass.getpass('Wiki password: ')

    # Create uploader
    uploader = WikiUploader(
        wiki_url=args.wiki_url,
        username=args.username,
        password=password,
        dry_run=args.dry_run
    )

    # Connect to wiki
    if not uploader.connect():
        return 1

    # Upload
    if args.single_page:
        # Upload single file
        wiki_file = Path(args.single_page)
        if wiki_file.exists():
            content = wiki_file.read_text(encoding='utf-8')
            page_name = wiki_file.stem.replace('-', '_').title()
            uploader.upload_page(page_name, content)
        else:
            print(f"Error: File not found: {args.single_page}")
            return 1
    else:
        # Upload directory
        uploader.upload_directory(args.input_dir, args.inventory)

    uploader.print_stats()
    return 0


if __name__ == '__main__':
    exit(main())
