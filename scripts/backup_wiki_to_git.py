#!/usr/bin/env python3
"""
backup_wiki_to_git.py - Export wiki-editable namespaces to Git

Backs up community-editable wiki content (Legacy, FAQ, etc.) to a Git repository.
This is a one-way backup - wiki is the source of truth for these namespaces.

Usage:
    python backup_wiki_to_git.py --wiki-url https://wiki.dreamfactory.com \
                                  --output ./wiki-backup \
                                  --namespaces V2 V3 V4 V5 V6 Legacy FAQ
"""

import os
import re
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

try:
    import mwclient
except ImportError:
    print("Error: mwclient not installed. Run: pip install mwclient")
    exit(1)


# Namespace IDs (must match LocalSettings.php configuration)
NAMESPACE_IDS = {
    'Main': 0,
    'V2': 3000,
    'V3': 3002,
    'V4': 3004,
    'V5': 3006,
    'V6': 3008,
    'Legacy': 3010,
    'FAQ': 3012,  # If created
    'Troubleshooting': 3014,  # If created
}


class WikiBackup:
    """Handles wiki content backup to Git."""

    def __init__(self, wiki_url: str, output_dir: str):
        self.wiki_url = wiki_url
        self.output_dir = Path(output_dir)
        self.site = None
        self.stats = {'exported': 0, 'failed': 0}

    def connect(self) -> bool:
        """Connect to MediaWiki (read-only, no login needed)."""
        try:
            host = self.wiki_url.replace('https://', '').replace('http://', '')
            self.site = mwclient.Site(host, scheme='https')
            print(f"✓ Connected to {self.wiki_url}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False

    def sanitize_filename(self, title: str) -> str:
        """Convert wiki page title to safe filename."""
        # Replace problematic characters
        filename = title.replace('/', '_')
        filename = re.sub(r'[<>:"|?*]', '_', filename)
        return filename + '.wiki'

    def export_page(self, page, output_path: Path) -> bool:
        """Export a single page to file."""
        try:
            content = page.text()
            if not content:
                return False

            # Add metadata header
            metadata = f"""{{{{{{-
  Title: {page.name}
  Last Modified: {page.touched}
  Namespace: {page.namespace}
  Exported: {datetime.utcnow().isoformat()}
-}}}}}}

"""
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(metadata + content, encoding='utf-8')
            return True

        except Exception as e:
            print(f"  ✗ Error exporting {page.name}: {e}")
            return False

    def export_namespace(self, namespace: str) -> int:
        """Export all pages in a namespace."""
        ns_id = NAMESPACE_IDS.get(namespace)
        if ns_id is None:
            print(f"  Warning: Unknown namespace '{namespace}', trying as-is")
            ns_id = namespace

        ns_dir = self.output_dir / namespace
        ns_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nExporting namespace: {namespace} (ID: {ns_id})")

        count = 0
        try:
            # Get all pages in namespace
            for page in self.site.allpages(namespace=ns_id):
                filename = self.sanitize_filename(page.name)
                output_path = ns_dir / filename

                if self.export_page(page, output_path):
                    count += 1
                    self.stats['exported'] += 1
                    if count % 10 == 0:
                        print(f"  Exported {count} pages...")
                else:
                    self.stats['failed'] += 1

        except Exception as e:
            print(f"  Error listing pages in {namespace}: {e}")

        print(f"  ✓ Exported {count} pages from {namespace}")
        return count

    def git_commit(self, message: str = None) -> bool:
        """Commit changes to Git repository."""
        if not message:
            message = f"Wiki backup {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"

        try:
            # Initialize repo if needed
            git_dir = self.output_dir / '.git'
            if not git_dir.exists():
                subprocess.run(['git', 'init'], cwd=self.output_dir, check=True)
                print("  Initialized new Git repository")

            # Add all changes
            subprocess.run(['git', 'add', '-A'], cwd=self.output_dir, check=True)

            # Check if there are changes to commit
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.output_dir,
                capture_output=True,
                text=True
            )

            if result.stdout.strip():
                # There are changes to commit
                subprocess.run(
                    ['git', 'commit', '-m', message],
                    cwd=self.output_dir,
                    check=True
                )
                print(f"  ✓ Committed: {message}")
                return True
            else:
                print("  No changes to commit")
                return False

        except subprocess.CalledProcessError as e:
            print(f"  ✗ Git error: {e}")
            return False

    def run_backup(self, namespaces: List[str], commit: bool = True) -> Dict:
        """Run full backup for specified namespaces."""
        print(f"Starting backup to {self.output_dir}")
        print(f"Namespaces: {', '.join(namespaces)}")

        for ns in namespaces:
            self.export_namespace(ns)

        if commit:
            self.git_commit()

        print(f"\n{'='*50}")
        print(f"Backup complete!")
        print(f"  Exported: {self.stats['exported']}")
        print(f"  Failed: {self.stats['failed']}")
        print(f"  Output: {self.output_dir}")
        print(f"{'='*50}")

        return self.stats


def main():
    parser = argparse.ArgumentParser(description='Backup wiki content to Git')
    parser.add_argument('--wiki-url', '-w', required=True,
                        help='MediaWiki URL')
    parser.add_argument('--output', '-o', default='./wiki-backup',
                        help='Output directory for backup')
    parser.add_argument('--namespaces', '-n', nargs='+',
                        default=['V2', 'V3', 'V4', 'V5', 'V6', 'Legacy'],
                        help='Namespaces to backup')
    parser.add_argument('--no-commit', action='store_true',
                        help='Skip Git commit')

    args = parser.parse_args()

    backup = WikiBackup(args.wiki_url, args.output)

    if not backup.connect():
        return 1

    stats = backup.run_backup(args.namespaces, commit=not args.no_commit)

    return 0 if stats['failed'] == 0 else 1


if __name__ == '__main__':
    exit(main())
