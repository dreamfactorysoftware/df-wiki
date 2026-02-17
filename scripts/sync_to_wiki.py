#!/usr/bin/env python3
"""
sync_to_wiki.py - Sync GitHub documentation to MediaWiki

Designed for CI/CD pipelines. Converts markdown to MediaWiki format
and deploys to the wiki, with conflict detection.

Usage:
    python sync_to_wiki.py --source docs/ --deploy
    python sync_to_wiki.py --verify
    python sync_to_wiki.py --check-conflicts

Environment variables:
    WIKI_URL - MediaWiki URL (e.g., https://wiki.dreamfactory.com)
    WIKI_USER - Bot username
    WIKI_PASSWORD - Bot password
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

try:
    import mwclient
    import yaml
except ImportError:
    print("Error: Missing dependencies. Run: pip install mwclient pyyaml")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
LAST_SYNC_FILE = SCRIPT_DIR / '.last_sync.json'


class WikiSyncer:
    """Handles GitHub → MediaWiki synchronization."""

    def __init__(self, wiki_url: str, username: str = None, password: str = None):
        self.wiki_url = wiki_url
        self.username = username
        self.password = password
        self.site = None
        self.last_sync = self._load_last_sync()

    def _load_last_sync(self) -> Dict:
        """Load last sync metadata."""
        if LAST_SYNC_FILE.exists():
            return json.loads(LAST_SYNC_FILE.read_text())
        return {'timestamp': None, 'pages': {}}

    def _save_last_sync(self):
        """Save sync metadata."""
        LAST_SYNC_FILE.write_text(json.dumps(self.last_sync, indent=2))

    def connect(self) -> bool:
        """Connect to MediaWiki."""
        try:
            url = self.wiki_url.replace('https://', '').replace('http://', '')
            host = url.split('/')[0]
            path = '/' + '/'.join(url.split('/')[1:]) if '/' in url else '/'
            if not path.endswith('/'):
                path += '/'

            scheme = 'https' if self.wiki_url.startswith('https://') else 'http'
            self.site = mwclient.Site(host, path=path, scheme=scheme)

            if self.username and self.password:
                self.site.login(self.username, self.password)
                print(f"✓ Connected as {self.username}")
            else:
                self.site.force_login = False
                print(f"✓ Connected anonymously to {host}")
            return True
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            return False

    def check_conflicts(self, pages: List[str], hours: int = 24) -> List[Dict]:
        """Check for wiki edits that would be overwritten."""
        if not self.site:
            self.connect()

        conflicts = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        for page_name in pages:
            page = self.site.pages[page_name]
            if page.exists:
                for rev in page.revisions(limit=1):
                    # mwclient returns time.struct_time objects
                    ts = rev['timestamp']
                    if isinstance(ts, time.struct_time):
                        rev_time = datetime(*ts[:6], tzinfo=timezone.utc)
                    else:
                        rev_time = datetime.strptime(
                            str(ts), '%Y-%m-%dT%H:%M:%SZ'
                        ).replace(tzinfo=timezone.utc)
                    if rev_time > cutoff:
                        # Check if this was our bot
                        if rev.get('user') != self.username:
                            conflicts.append({
                                'page': page_name,
                                'editor': rev.get('user', 'unknown'),
                                'timestamp': rev_time.isoformat(),
                                'comment': rev.get('comment', '')
                            })

        return conflicts

    def convert_markdown_to_wiki(self, md_file: Path) -> Optional[str]:
        """Convert markdown file to MediaWiki format using pandoc."""
        try:
            result = subprocess.run(
                ['pandoc', '-f', 'markdown', '-t', 'mediawiki', str(md_file)],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Pandoc conversion failed: {e.stderr}")
            return None
        except FileNotFoundError:
            print("  ✗ Pandoc not installed")
            return None

    def get_page_name_from_path(self, file_path: Path, source_dir: Path) -> str:
        """Generate wiki page name from file path."""
        rel_path = file_path.relative_to(source_dir)
        # Remove file extension (.md or .wiki)
        name = str(rel_path.with_suffix(''))
        # Convert path separators to wiki subpages
        name = name.replace('/', '/')
        # Convert hyphens to underscores, title case
        parts = name.split('/')
        wiki_name = '/'.join(
            '_'.join(word.capitalize() for word in part.replace('-', '_').split('_'))
            for part in parts
        )
        return wiki_name

    def deploy_page(self, page_name: str, content: str, summary: str = None) -> bool:
        """Deploy a single page to wiki."""
        if not summary:
            summary = "Automated sync from GitHub"

        try:
            page = self.site.pages[page_name]
            page.save(content, summary=summary)
            print(f"  ✓ {page_name}")
            return True
        except Exception as e:
            print(f"  ✗ {page_name}: {e}")
            return False

    def sync_directory(self, source_dir: str, dry_run: bool = False, force: bool = False) -> Dict:
        """Sync all wiki/markdown files from directory to wiki."""
        source_path = Path(source_dir)
        stats = {'success': 0, 'failed': 0, 'skipped': 0}

        if not source_path.exists():
            print(f"Error: Source directory not found: {source_dir}")
            return stats

        # Collect both .wiki and .md files
        source_files = sorted(
            list(source_path.rglob('*.wiki')) + list(source_path.rglob('*.md'))
        )
        print(f"\nSyncing {len(source_files)} files from {source_dir}")

        # Check for conflicts first
        page_names = [
            self.get_page_name_from_path(f, source_path)
            for f in source_files
        ]
        conflicts = self.check_conflicts(page_names, hours=24)

        if conflicts:
            print("\n⚠️  WARNING: Potential conflicts detected!")
            for c in conflicts:
                print(f"  - {c['page']} edited by {c['editor']} at {c['timestamp']}")
            if not dry_run:
                if force:
                    print("\n--force set, proceeding despite conflicts.")
                elif sys.stdin.isatty():
                    response = input("\nProceed anyway? (y/N): ")
                    if response.lower() != 'y':
                        print("Sync cancelled.")
                        return stats
                else:
                    print("\nConflicts detected in non-interactive mode. Use --force to override.")
                    print("Sync cancelled.")
                    return stats

        print("\nDeploying pages:")
        for src_file in source_files:
            if src_file.name.startswith('.') or src_file.name == '_ai-reference.md':
                stats['skipped'] += 1
                continue

            page_name = self.get_page_name_from_path(src_file, source_path)

            if dry_run:
                print(f"  [DRY RUN] Would deploy: {page_name}")
                stats['success'] += 1
                continue

            # .wiki files are already MediaWiki markup; .md files need conversion
            if src_file.suffix == '.wiki':
                wiki_content = src_file.read_text(encoding='utf-8')
            else:
                wiki_content = self.convert_markdown_to_wiki(src_file)

            if wiki_content:
                if self.deploy_page(page_name, wiki_content):
                    stats['success'] += 1
                    self.last_sync['pages'][page_name] = {
                        'source': str(src_file),
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                else:
                    stats['failed'] += 1
            else:
                stats['failed'] += 1

        self.last_sync['timestamp'] = datetime.now(timezone.utc).isoformat()
        self._save_last_sync()

        print(f"\n✓ Sync complete: {stats['success']} success, {stats['failed']} failed, {stats['skipped']} skipped")
        return stats

    def verify_deployment(self) -> bool:
        """Verify that deployed pages exist and are accessible."""
        if not self.last_sync['pages']:
            print("No previous sync to verify.")
            return True

        print(f"\nVerifying {len(self.last_sync['pages'])} pages...")
        errors = []

        for page_name in self.last_sync['pages']:
            page = self.site.pages[page_name]
            if not page.exists:
                errors.append(page_name)
                print(f"  ✗ {page_name} - NOT FOUND")
            else:
                print(f"  ✓ {page_name}")

        if errors:
            print(f"\n✗ Verification failed: {len(errors)} pages missing")
            return False
        else:
            print("\n✓ All pages verified successfully")
            return True


def main():
    parser = argparse.ArgumentParser(description='Sync GitHub docs to MediaWiki')
    parser.add_argument('--source', '-s', help='Source directory with markdown files')
    parser.add_argument('--deploy', '-d', action='store_true', help='Deploy to wiki')
    parser.add_argument('--verify', '-v', action='store_true', help='Verify deployment')
    parser.add_argument('--check-conflicts', '-c', action='store_true',
                        help='Check for wiki conflicts')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Show what would be done')
    parser.add_argument('--force', '-f', action='store_true',
                        help='Deploy despite conflicts (for CI/CD)')
    parser.add_argument('--wiki-url', help='Wiki URL (or WIKI_URL env var)')
    parser.add_argument('--username', '-u', help='Wiki username (or WIKI_USER env var)')
    parser.add_argument('--password', '-p', help='Wiki password (or WIKI_PASSWORD env var)')

    args = parser.parse_args()

    # Get credentials from args or environment
    wiki_url = args.wiki_url or os.environ.get('WIKI_URL', 'https://wiki.dreamfactory.com')
    username = args.username or os.environ.get('WIKI_USER')
    password = args.password or os.environ.get('WIKI_PASSWORD')

    syncer = WikiSyncer(wiki_url, username, password)

    if not syncer.connect():
        return 1

    if args.check_conflicts:
        # Check for conflicts in common pages
        conflicts = syncer.check_conflicts([
            'Main_Page', 'Docker_Installation', 'Linux_Installation'
        ])
        if conflicts:
            print("Conflicts found:")
            for c in conflicts:
                print(f"  {c['page']}: {c['editor']} at {c['timestamp']}")
            return 1
        else:
            print("No conflicts detected.")
            return 0

    if args.verify:
        return 0 if syncer.verify_deployment() else 1

    if args.deploy and args.source:
        stats = syncer.sync_directory(args.source, dry_run=args.dry_run, force=args.force)
        return 0 if stats['failed'] == 0 else 1

    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
