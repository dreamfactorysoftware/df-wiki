#!/usr/bin/env python3
"""
generate_old_wiki_redirects.py - Generate redirect/hub/stub .wiki files for old wiki URLs

Reads old_wiki_redirect_map.json and creates .wiki files in docs/redirects/
that preserve old wiki URLs by redirecting to new content pages.

Also updates docs/page_map.json so the CI/CD pipeline deploys them with
the correct wiki page names (using / path separators).

Usage:
    python generate_old_wiki_redirects.py [--map-file MAP] [--output-dir DIR] [--dry-run]
"""

import json
import argparse
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
DEFAULT_MAP_FILE = SCRIPT_DIR / 'old_wiki_redirect_map.json'
DEFAULT_OUTPUT_DIR = SCRIPT_DIR.parent / 'docs' / 'redirects'
PAGE_MAP_FILE = SCRIPT_DIR.parent / 'docs' / 'page_map.json'


def sanitize_filename(old_path: str) -> str:
    """Convert an old wiki path to a safe filename.

    Replaces / with _ to create a flat file structure in docs/redirects/.
    """
    return old_path.replace('/', '_') + '.wiki'


def generate_redirect_content(target: str) -> str:
    """Generate MediaWiki redirect markup."""
    return f'#REDIRECT [[{target}]]\n'


def generate_hub_content(old_path: str, links: list) -> str:
    """Generate a hub page with links to related new pages."""
    # Derive a readable title from the old path
    title = old_path.split('/')[-1].replace('_', ' ')

    lines = [
        f'= {title} =',
        '',
        f'This page lists documentation related to DreamFactory {title.lower()}.',
        '',
    ]

    for link in links:
        lines.append(f'* [[{link["target"]}|{link["label"]}]]')

    lines.append('')
    lines.append('[[Category:Navigation]]')
    lines.append('')
    return '\n'.join(lines)


def generate_stub_content(entry: dict) -> str:
    """Generate a stub page with introductory content and links."""
    title = entry.get('stub_title', entry['old_path'].split('/')[-1].replace('_', ' '))
    content_text = entry.get('stub_content', f'Content for {title} is being developed.')
    links = entry.get('stub_links', [])

    lines = [
        f'= {title} =',
        '',
        content_text,
        '',
    ]

    if links:
        lines.append('== Related Pages ==')
        lines.append('')
        for link in links:
            lines.append(f'* [[{link["target"]}|{link["label"]}]]')
        lines.append('')

    lines.append('[[Category:Navigation]]')
    lines.append('')
    return '\n'.join(lines)


def load_page_map() -> dict:
    """Load the existing page_map.json."""
    if PAGE_MAP_FILE.exists():
        return json.loads(PAGE_MAP_FILE.read_text(encoding='utf-8'))
    return {}


def save_page_map(page_map: dict):
    """Save page_map.json with sorted keys."""
    PAGE_MAP_FILE.write_text(
        json.dumps(page_map, indent=2, sort_keys=True, ensure_ascii=False) + '\n',
        encoding='utf-8'
    )


def main():
    parser = argparse.ArgumentParser(
        description='Generate redirect .wiki files for old wiki URLs'
    )
    parser.add_argument('--map-file', '-m', type=Path, default=DEFAULT_MAP_FILE,
                        help='Path to redirect map JSON')
    parser.add_argument('--output-dir', '-o', type=Path, default=DEFAULT_OUTPUT_DIR,
                        help='Output directory for .wiki files')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Show what would be generated without writing files')
    args = parser.parse_args()

    # Load redirect map
    if not args.map_file.exists():
        print(f'Error: Map file not found: {args.map_file}')
        return 1

    entries = json.loads(args.map_file.read_text(encoding='utf-8'))

    # Create output directory
    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load existing page_map.json
    page_map = load_page_map()

    stats = {'redirect': 0, 'redirect-closest': 0, 'hub': 0, 'stub': 0, 'no-action': 0}
    generated_files = []

    for entry in entries:
        strategy = entry['strategy']
        old_path = entry['old_path']
        rank = entry['rank']
        stats[strategy] = stats.get(strategy, 0) + 1

        if strategy == 'no-action':
            print(f'  [SKIP] Rank {rank}: {old_path} (no action needed)')
            continue

        filename = sanitize_filename(old_path)
        filepath = args.output_dir / filename
        # The page_map key is relative to the docs/ directory
        page_map_key = f'redirects/{filename}'
        # The wiki page name uses the original old path (with / separators)
        wiki_page_name = old_path

        if strategy in ('redirect', 'redirect-closest'):
            content = generate_redirect_content(entry['new_target'])
            label = 'REDIRECT' if strategy == 'redirect' else 'REDIRECT-CLOSEST'
            print(f'  [{label}] Rank {rank}: {old_path} -> {entry["new_target"]}')

        elif strategy == 'hub':
            content = generate_hub_content(old_path, entry.get('hub_links', []))
            print(f'  [HUB] Rank {rank}: {old_path} ({len(entry.get("hub_links", []))} links)')

        elif strategy == 'stub':
            content = generate_stub_content(entry)
            print(f'  [STUB] Rank {rank}: {old_path}')

        else:
            print(f'  [UNKNOWN] Rank {rank}: {old_path} (strategy: {strategy})')
            continue

        if not args.dry_run:
            filepath.write_text(content, encoding='utf-8')
            page_map[page_map_key] = wiki_page_name

        generated_files.append({
            'filename': filename,
            'wiki_page': wiki_page_name,
            'strategy': strategy,
            'rank': rank
        })

    # Save updated page_map.json
    if not args.dry_run:
        save_page_map(page_map)

    # Print summary
    print(f'\n{"=" * 60}')
    print('Generation Summary')
    print(f'{"=" * 60}')
    print(f'  Redirects:         {stats.get("redirect", 0)}')
    print(f'  Redirect-closest:  {stats.get("redirect-closest", 0)}')
    print(f'  Hubs:              {stats.get("hub", 0)}')
    print(f'  Stubs:             {stats.get("stub", 0)}')
    print(f'  No-action:         {stats.get("no-action", 0)}')
    print(f'  Total files:       {len(generated_files)}')
    if args.dry_run:
        print(f'  (DRY RUN - no files written)')
    else:
        print(f'  Output directory:  {args.output_dir}')
        print(f'  Updated:           {PAGE_MAP_FILE}')
    print(f'{"=" * 60}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
