#!/usr/bin/env python3
"""
rollback_old_wiki_redirects.py - Delete all redirect/hub/stub pages created for old wiki URLs

Reads the redirect map and deletes every page that was created by
generate_old_wiki_redirects.py. Safe because deleting redirects only
returns those old URLs to 404 — it doesn't affect any real content pages.

Requires sysop/admin permissions (page.delete() needs 'delete' right).

Usage:
    python rollback_old_wiki_redirects.py --wiki-url http://localhost:8082
    python rollback_old_wiki_redirects.py --wiki-url http://localhost:8082 --dry-run
"""

import json
import argparse
import sys
from pathlib import Path

try:
    import mwclient
except ImportError:
    print("Error: mwclient not installed. Run: pip install mwclient")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
DEFAULT_MAP_FILE = SCRIPT_DIR / 'old_wiki_redirect_map.json'
PAGE_MAP_FILE = SCRIPT_DIR.parent / 'docs' / 'page_map.json'
REDIRECTS_DIR = SCRIPT_DIR.parent / 'docs' / 'redirects'


def connect_wiki(wiki_url: str, username: str = None, password: str = None):
    """Connect to the MediaWiki site."""
    url = wiki_url.replace('https://', '').replace('http://', '')
    host = url.split('/')[0]
    path = '/' + '/'.join(url.split('/')[1:]) if '/' in url else '/'
    if not path.endswith('/'):
        path += '/'

    scheme = 'https' if wiki_url.startswith('https://') else 'http'
    site = mwclient.Site(host, path=path, scheme=scheme)

    if username and password:
        site.login(username, password)
    else:
        site.force_login = False

    return site


def main():
    parser = argparse.ArgumentParser(
        description='Rollback old wiki redirect pages'
    )
    parser.add_argument('--wiki-url', '-w', required=True,
                        help='MediaWiki URL (e.g., http://localhost:8082)')
    parser.add_argument('--map-file', '-m', type=Path, default=DEFAULT_MAP_FILE,
                        help='Path to redirect map JSON')
    parser.add_argument('--username', '-u', help='Wiki username (needs sysop)')
    parser.add_argument('--password', '-p', help='Wiki password')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Show what would be deleted without deleting')
    parser.add_argument('--clean-files', action='store_true',
                        help='Also delete local .wiki files and page_map.json entries')
    args = parser.parse_args()

    # Load redirect map
    if not args.map_file.exists():
        print(f'Error: Map file not found: {args.map_file}')
        return 1

    entries = json.loads(args.map_file.read_text(encoding='utf-8'))

    # Filter to only entries that created pages
    actionable = [e for e in entries if e['strategy'] != 'no-action']

    if not actionable:
        print('No pages to roll back.')
        return 0

    # Connect to wiki
    print(f'Connecting to {args.wiki_url}...')
    try:
        site = connect_wiki(args.wiki_url, args.username, args.password)
    except Exception as e:
        print(f'Error connecting: {e}')
        return 1
    print('Connected.\n')

    # Delete pages
    deleted = 0
    not_found = 0
    failed = 0

    for entry in actionable:
        old_path = entry['old_path']
        page = site.pages[old_path]

        if not page.exists:
            print(f'  [SKIP] {old_path} (does not exist)')
            not_found += 1
            continue

        if args.dry_run:
            print(f'  [DRY RUN] Would delete: {old_path}')
            deleted += 1
            continue

        try:
            page.delete(reason='Rollback: removing old wiki redirect/hub/stub page')
            print(f'  [DELETED] {old_path}')
            deleted += 1
        except mwclient.errors.APIError as e:
            if 'permissiondenied' in str(e).lower() or 'cantdelete' in str(e).lower():
                print(f'  [FAIL] {old_path} (permission denied - needs sysop)')
            else:
                print(f'  [FAIL] {old_path} ({e})')
            failed += 1
        except Exception as e:
            print(f'  [FAIL] {old_path} ({e})')
            failed += 1

    # Optionally clean up local files
    if args.clean_files and not args.dry_run:
        print('\nCleaning up local files...')
        page_map = {}
        if PAGE_MAP_FILE.exists():
            page_map = json.loads(PAGE_MAP_FILE.read_text(encoding='utf-8'))

        files_removed = 0
        for entry in actionable:
            old_path = entry['old_path']
            filename = old_path.replace('/', '_') + '.wiki'
            filepath = REDIRECTS_DIR / filename
            page_map_key = f'redirects/{filename}'

            if filepath.exists():
                filepath.unlink()
                files_removed += 1

            page_map.pop(page_map_key, None)

        # Save updated page_map
        PAGE_MAP_FILE.write_text(
            json.dumps(page_map, indent=2, sort_keys=True, ensure_ascii=False) + '\n',
            encoding='utf-8'
        )
        print(f'  Removed {files_removed} local .wiki files')
        print(f'  Updated {PAGE_MAP_FILE}')

    # Summary
    print(f'\n{"=" * 60}')
    print('Rollback Summary')
    print(f'{"=" * 60}')
    print(f'  Deleted:    {deleted}')
    print(f'  Not found:  {not_found}')
    print(f'  Failed:     {failed}')
    if args.dry_run:
        print(f'  (DRY RUN - no pages actually deleted)')
    print(f'{"=" * 60}')

    return 1 if failed > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
