#!/usr/bin/env python3
"""
extract_legacy_pages.py - Extract content from legacy MediaWiki instance

Connects to the legacy wiki Docker container and extracts selected pages
as clean markdown files for import into the Git repository.

Usage:
    # List all pages (generate inventory)
    python extract_legacy_pages.py --wiki-url http://localhost:8081 --list-only

    # Export specific pages
    python extract_legacy_pages.py --wiki-url http://localhost:8081 \
        --pages "Installation,Configuration" --output ./legacy-content/

    # Export from inventory CSV (filtered)
    python extract_legacy_pages.py --wiki-url http://localhost:8081 \
        --inventory legacy_page_inventory.csv --filter-status MIGRATE \
        --output ./legacy-content/
"""

import os
import re
import csv
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests")
    exit(1)


class LegacyWikiExtractor:
    """Extracts content from legacy MediaWiki instance."""

    def __init__(self, wiki_url: str):
        self.wiki_url = wiki_url.rstrip('/')
        self.api_url = f"{self.wiki_url}/api.php"
        self.session = requests.Session()

    def test_connection(self) -> bool:
        """Test connection to the wiki."""
        try:
            response = self.session.get(
                self.api_url,
                params={'action': 'query', 'meta': 'siteinfo', 'format': 'json'},
                timeout=10
            )
            data = response.json()
            sitename = data.get('query', {}).get('general', {}).get('sitename', 'Unknown')
            print(f"✓ Connected to: {sitename}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False

    def get_all_pages(self, namespace: int = 0) -> List[Dict]:
        """Get list of all pages in a namespace."""
        pages = []
        params = {
            'action': 'query',
            'list': 'allpages',
            'apnamespace': namespace,
            'aplimit': 500,
            'format': 'json'
        }

        while True:
            response = self.session.get(self.api_url, params=params, timeout=30)
            data = response.json()

            for page in data.get('query', {}).get('allpages', []):
                pages.append({
                    'pageid': page['pageid'],
                    'title': page['title'],
                    'namespace': namespace
                })

            # Handle pagination
            if 'continue' in data:
                params['apcontinue'] = data['continue']['apcontinue']
            else:
                break

        return pages

    def get_page_info(self, title: str) -> Optional[Dict]:
        """Get detailed info about a page."""
        params = {
            'action': 'query',
            'titles': title,
            'prop': 'info|revisions',
            'rvprop': 'timestamp|user|size',
            'format': 'json'
        }

        try:
            response = self.session.get(self.api_url, params=params, timeout=10)
            data = response.json()
            pages = data.get('query', {}).get('pages', {})

            for pageid, page_data in pages.items():
                if pageid == '-1':
                    return None

                revisions = page_data.get('revisions', [{}])
                return {
                    'pageid': pageid,
                    'title': page_data.get('title'),
                    'last_modified': revisions[0].get('timestamp', ''),
                    'last_editor': revisions[0].get('user', ''),
                    'size': revisions[0].get('size', 0)
                }

        except Exception as e:
            print(f"  Error getting info for {title}: {e}")
            return None

    def get_page_content(self, title: str) -> Optional[str]:
        """Get raw wikitext content of a page."""
        params = {
            'action': 'query',
            'titles': title,
            'prop': 'revisions',
            'rvprop': 'content',
            'rvslots': 'main',
            'format': 'json'
        }

        try:
            response = self.session.get(self.api_url, params=params, timeout=30)
            data = response.json()
            pages = data.get('query', {}).get('pages', {})

            for pageid, page_data in pages.items():
                if pageid == '-1':
                    return None

                revisions = page_data.get('revisions', [])
                if revisions:
                    slots = revisions[0].get('slots', {})
                    main = slots.get('main', {})
                    return main.get('*', '')

        except Exception as e:
            print(f"  Error getting content for {title}: {e}")

        return None

    def wikitext_to_markdown(self, wikitext: str, title: str = '') -> str:
        """Convert MediaWiki syntax to Markdown (basic conversion)."""
        content = wikitext

        # Headers: == Title == -> ## Title
        content = re.sub(r'^======\s*(.+?)\s*======', r'###### \1', content, flags=re.MULTILINE)
        content = re.sub(r'^=====\s*(.+?)\s*=====', r'##### \1', content, flags=re.MULTILINE)
        content = re.sub(r'^====\s*(.+?)\s*====', r'#### \1', content, flags=re.MULTILINE)
        content = re.sub(r'^===\s*(.+?)\s*===', r'### \1', content, flags=re.MULTILINE)
        content = re.sub(r'^==\s*(.+?)\s*==', r'## \1', content, flags=re.MULTILINE)
        content = re.sub(r'^=\s*(.+?)\s*=', r'# \1', content, flags=re.MULTILINE)

        # Bold: '''text''' -> **text**
        content = re.sub(r"'''(.+?)'''", r'**\1**', content)

        # Italic: ''text'' -> *text*
        content = re.sub(r"''(.+?)''", r'*\1*', content)

        # Internal links: [[Page|Text]] -> [Text](Page)
        content = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'[\2](\1)', content)
        content = re.sub(r'\[\[([^\]]+)\]\]', r'[\1](\1)', content)

        # External links: [url text] -> [text](url)
        content = re.sub(r'\[(\S+)\s+([^\]]+)\]', r'[\2](\1)', content)

        # Code blocks: <syntaxhighlight lang="x">...</syntaxhighlight> -> ```x...```
        content = re.sub(
            r'<syntaxhighlight[^>]*lang="?(\w+)"?[^>]*>(.*?)</syntaxhighlight>',
            r'```\1\n\2\n```',
            content,
            flags=re.DOTALL
        )

        # Pre blocks: <pre>...</pre> -> ```...```
        content = re.sub(r'<pre>(.*?)</pre>', r'```\n\1\n```', content, flags=re.DOTALL)

        # Code: <code>...</code> -> `...`
        content = re.sub(r'<code>(.+?)</code>', r'`\1`', content)

        # Lists: * item -> - item
        content = re.sub(r'^\*\s+', r'- ', content, flags=re.MULTILINE)

        # Numbered lists: # item -> 1. item
        content = re.sub(r'^#\s+', r'1. ', content, flags=re.MULTILINE)

        # Remove categories
        content = re.sub(r'\[\[Category:[^\]]+\]\]', '', content)

        # Remove templates (basic - may need manual cleanup)
        content = re.sub(r'\{\{[^}]+\}\}', '', content)

        # Clean up multiple blank lines
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Add frontmatter
        frontmatter = f"""---
title: "{title}"
source: legacy-wiki
extracted: {datetime.utcnow().isoformat()}
---

"""
        return frontmatter + content.strip()

    def generate_inventory(self, output_file: str):
        """Generate inventory CSV of all wiki pages."""
        print("Generating page inventory...")

        pages = self.get_all_pages(namespace=0)  # Main namespace
        print(f"Found {len(pages)} pages")

        inventory = []
        for i, page in enumerate(pages):
            if i % 20 == 0:
                print(f"  Processing {i}/{len(pages)}...")

            info = self.get_page_info(page['title'])
            if info:
                inventory.append({
                    'pageid': info['pageid'],
                    'title': info['title'],
                    'last_modified': info['last_modified'],
                    'last_editor': info['last_editor'],
                    'size_bytes': info['size'],
                    'status': 'REVIEW',  # Default status
                    'version': '',  # To be filled manually
                    'notes': ''
                })

        # Write CSV
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'pageid', 'title', 'last_modified', 'last_editor',
                'size_bytes', 'status', 'version', 'notes'
            ])
            writer.writeheader()
            writer.writerows(inventory)

        print(f"✓ Inventory written to: {output_file}")
        print(f"  Total pages: {len(inventory)}")
        print("\nEdit the CSV and set 'status' column to:")
        print("  MIGRATE - Include in new wiki")
        print("  SKIP    - Do not migrate")
        print("  REVIEW  - Needs manual inspection")

    def export_pages(self, pages: List[str], output_dir: str, format: str = 'markdown'):
        """Export specified pages to files."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        exported = 0
        failed = 0

        for title in pages:
            print(f"  Exporting: {title}...", end=' ')

            content = self.get_page_content(title)
            if not content:
                print("FAILED (no content)")
                failed += 1
                continue

            # Convert to markdown if requested
            if format == 'markdown':
                content = self.wikitext_to_markdown(content, title)
                ext = '.md'
            else:
                ext = '.wiki'

            # Create safe filename
            filename = re.sub(r'[<>:"/\\|?*]', '_', title) + ext
            filepath = output_path / filename

            filepath.write_text(content, encoding='utf-8')
            print("OK")
            exported += 1

        print(f"\n✓ Export complete: {exported} succeeded, {failed} failed")
        print(f"  Output directory: {output_dir}")

    def export_from_inventory(self, inventory_file: str, output_dir: str,
                              filter_status: str = 'MIGRATE', format: str = 'markdown'):
        """Export pages based on inventory CSV."""
        with open(inventory_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            pages = [
                row['title']
                for row in reader
                if row.get('status', '').upper() == filter_status.upper()
            ]

        if not pages:
            print(f"No pages with status '{filter_status}' found in inventory")
            return

        print(f"Found {len(pages)} pages with status '{filter_status}'")
        self.export_pages(pages, output_dir, format)


def main():
    parser = argparse.ArgumentParser(description='Extract content from legacy MediaWiki')
    parser.add_argument('--wiki-url', '-w', default='http://localhost:8081',
                        help='Legacy wiki URL')
    parser.add_argument('--list-only', '-l', action='store_true',
                        help='Only generate page inventory, do not export')
    parser.add_argument('--pages', '-p',
                        help='Comma-separated list of page titles to export')
    parser.add_argument('--inventory', '-i',
                        help='Inventory CSV file (use with --filter-status)')
    parser.add_argument('--filter-status', '-f', default='MIGRATE',
                        help='Status to filter from inventory (default: MIGRATE)')
    parser.add_argument('--output', '-o', default='./legacy-content',
                        help='Output directory')
    parser.add_argument('--format', choices=['markdown', 'wiki'], default='markdown',
                        help='Output format (default: markdown)')

    args = parser.parse_args()

    extractor = LegacyWikiExtractor(args.wiki_url)

    if not extractor.test_connection():
        print("\nMake sure the legacy wiki Docker container is running:")
        print("  docker-compose -f docker-compose.legacy-wiki.yml up -d")
        return 1

    if args.list_only:
        inventory_file = Path(args.output).with_suffix('.csv')
        if inventory_file.suffix != '.csv':
            inventory_file = Path(f"{args.output}/legacy_page_inventory.csv")
        inventory_file.parent.mkdir(parents=True, exist_ok=True)
        extractor.generate_inventory(str(inventory_file))

    elif args.inventory:
        extractor.export_from_inventory(
            args.inventory, args.output, args.filter_status, args.format
        )

    elif args.pages:
        pages = [p.strip() for p in args.pages.split(',')]
        extractor.export_pages(pages, args.output, args.format)

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
