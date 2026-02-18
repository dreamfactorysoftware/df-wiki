#!/usr/bin/env python3
"""
verify_old_wiki_redirects.py - Verify old wiki URL redirects on the wiki

Queries the MediaWiki API to verify:
- Every redirect page exists
- Redirect targets exist and return content
- Hub pages have valid internal links
- Reports pass/fail per old URL with the old traffic rank

Usage:
    python verify_old_wiki_redirects.py --wiki-url http://localhost:8082
    python verify_old_wiki_redirects.py --wiki-url https://wiki.dreamfactory.com
"""

import json
import re
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


def extract_redirect_target(text: str):
    """Extract redirect target from wiki markup."""
    match = re.match(r'#REDIRECT\s*\[\[([^\]]+)\]\]', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def extract_wiki_links(text: str):
    """Extract all internal wiki links from markup."""
    return re.findall(r'\[\[([^|\]]+)(?:\|[^\]]+)?\]\]', text)


def verify_entry(site, entry: dict) -> dict:
    """Verify a single redirect map entry. Returns a result dict."""
    strategy = entry['strategy']
    old_path = entry['old_path']
    rank = entry['rank']
    views = entry['views']

    result = {
        'rank': rank,
        'old_path': old_path,
        'views': views,
        'strategy': strategy,
        'status': 'PASS',
        'details': ''
    }

    if strategy == 'no-action':
        result['details'] = 'Skipped (no action needed)'
        return result

    # Check that the redirect/hub/stub page exists at the old path
    page = site.pages[old_path]
    if not page.exists:
        result['status'] = 'FAIL'
        result['details'] = f'Page "{old_path}" does not exist on wiki'
        return result

    page_text = page.text()

    if strategy in ('redirect', 'redirect-closest'):
        expected_target = entry['new_target']

        # Check it's actually a redirect
        actual_target = extract_redirect_target(page_text)
        if not actual_target:
            result['status'] = 'FAIL'
            result['details'] = f'Page exists but is not a redirect'
            return result

        # Normalize for comparison (MediaWiki is case-insensitive for first char)
        if actual_target.replace(' ', '_') != expected_target.replace(' ', '_'):
            result['status'] = 'WARN'
            result['details'] = f'Redirect target mismatch: expected "{expected_target}", got "{actual_target}"'
            # Still check if the actual target exists
            expected_target = actual_target

        # Verify target page exists
        target_page = site.pages[expected_target]
        if not target_page.exists:
            result['status'] = 'FAIL'
            result['details'] = f'Redirect target "{expected_target}" does not exist'
            return result

        # Verify target has content (not empty)
        target_text = target_page.text()
        if not target_text or len(target_text.strip()) < 10:
            result['status'] = 'WARN'
            result['details'] = f'Redirect target "{expected_target}" exists but has minimal content ({len(target_text)} chars)'
            return result

        if result['status'] == 'PASS':
            result['details'] = f'-> {expected_target} (OK)'

    elif strategy == 'hub':
        # Verify hub page has links
        links = extract_wiki_links(page_text)
        if not links:
            result['status'] = 'WARN'
            result['details'] = 'Hub page has no internal links'
            return result

        # Verify linked pages exist
        missing_targets = []
        for link_target in links:
            # Skip category links
            if link_target.startswith('Category:'):
                continue
            target_page = site.pages[link_target]
            if not target_page.exists:
                missing_targets.append(link_target)

        if missing_targets:
            result['status'] = 'WARN'
            result['details'] = f'Hub has {len(missing_targets)} missing link targets: {", ".join(missing_targets[:3])}'
            if len(missing_targets) > 3:
                result['details'] += f'... (+{len(missing_targets) - 3} more)'
        else:
            result['details'] = f'Hub with {len(links)} valid links'

    elif strategy == 'stub':
        # Verify stub page has some content
        if len(page_text.strip()) < 20:
            result['status'] = 'WARN'
            result['details'] = 'Stub page has very little content'
            return result

        # Check if stub links resolve
        links = extract_wiki_links(page_text)
        missing = [l for l in links if not l.startswith('Category:') and not site.pages[l].exists]
        if missing:
            result['status'] = 'WARN'
            result['details'] = f'Stub has {len(missing)} missing link targets: {", ".join(missing[:3])}'
        else:
            result['details'] = f'Stub with {len(links)} links (OK)'

    return result


def main():
    parser = argparse.ArgumentParser(
        description='Verify old wiki URL redirects on the wiki'
    )
    parser.add_argument('--wiki-url', '-w', required=True,
                        help='MediaWiki URL (e.g., http://localhost:8082)')
    parser.add_argument('--map-file', '-m', type=Path, default=DEFAULT_MAP_FILE,
                        help='Path to redirect map JSON')
    parser.add_argument('--username', '-u', help='Wiki username')
    parser.add_argument('--password', '-p', help='Wiki password')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show details for all entries, not just failures')
    args = parser.parse_args()

    # Load redirect map
    if not args.map_file.exists():
        print(f'Error: Map file not found: {args.map_file}')
        return 1

    entries = json.loads(args.map_file.read_text(encoding='utf-8'))

    # Connect to wiki
    print(f'Connecting to {args.wiki_url}...')
    try:
        site = connect_wiki(args.wiki_url, args.username, args.password)
    except Exception as e:
        print(f'Error connecting: {e}')
        return 1
    print('Connected.\n')

    # Verify each entry
    results = []
    for entry in entries:
        result = verify_entry(site, entry)
        results.append(result)

        # Print progress
        icon = {'PASS': 'OK', 'FAIL': 'FAIL', 'WARN': 'WARN'}[result['status']]
        if result['status'] != 'PASS' or args.verbose:
            print(f'  [{icon}] Rank {result["rank"]}: {result["old_path"]} - {result["details"]}')
        elif result['strategy'] != 'no-action':
            print(f'  [{icon}] Rank {result["rank"]}: {result["old_path"]}')

    # Summary
    passes = sum(1 for r in results if r['status'] == 'PASS')
    fails = sum(1 for r in results if r['status'] == 'FAIL')
    warns = sum(1 for r in results if r['status'] == 'WARN')
    no_actions = sum(1 for r in results if r['strategy'] == 'no-action')
    actionable = len(results) - no_actions

    print(f'\n{"=" * 60}')
    print('Verification Summary')
    print(f'{"=" * 60}')
    print(f'  Total entries:    {len(results)}')
    print(f'  No-action:        {no_actions}')
    print(f'  Actionable:       {actionable}')
    print(f'  PASS:             {passes}')
    print(f'  WARN:             {warns}')
    print(f'  FAIL:             {fails}')

    if fails > 0:
        pct = (actionable - fails) / max(actionable, 1) * 100
        print(f'\n  Pass rate: {pct:.1f}% ({actionable - fails}/{actionable})')
        print(f'\n  FAILURES:')
        for r in results:
            if r['status'] == 'FAIL':
                print(f'    Rank {r["rank"]} ({r["views"]} views): {r["old_path"]}')
                print(f'      {r["details"]}')
        print(f'{"=" * 60}')
        return 1
    else:
        print(f'\n  Pass rate: 100% ({actionable}/{actionable})')
        print(f'{"=" * 60}')
        return 0


if __name__ == '__main__':
    sys.exit(main())
