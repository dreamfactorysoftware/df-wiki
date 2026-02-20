#!/usr/bin/env python3
"""
deploy_templates.py - Deploy MediaWiki templates from git to the wiki

Uploads .wiki files from mediawiki_templates/ and main_page_templates/
to the Template: namespace on the wiki.

Template files must be named Template_<Name>.wiki and will be uploaded
as Template:<Name> (underscores in the prefix become a colon separator).
Non-template files (e.g., CSS) are uploaded to the MediaWiki: namespace.

Usage:
    python deploy_templates.py [--dry-run]
    python deploy_templates.py --wiki-url http://localhost:8082
"""

import os
import sys
import argparse
from pathlib import Path

try:
    import mwclient
except ImportError:
    print("Error: mwclient not installed. Run: pip install mwclient")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).parent
TEMPLATE_DIRS = [
    SCRIPT_DIR / 'mediawiki_templates',
    SCRIPT_DIR / 'main_page_templates',
]


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


def get_page_name(filepath: Path) -> str:
    """Derive the wiki page name from a template file path.

    Template_Foo.wiki -> Template:Foo
    Template_FooBar.wiki -> Template:FooBar
    MainPage.css -> MediaWiki:MainPage.css
    Sidebar.wiki -> MediaWiki:Sidebar
    MainPage.wiki -> Template:MainPage
    """
    stem = filepath.stem
    suffix = filepath.suffix

    # Files that map to MediaWiki: namespace (system pages)
    MEDIAWIKI_PAGES = {'Sidebar'}

    if stem in MEDIAWIKI_PAGES and suffix == '.wiki':
        return f'MediaWiki:{stem}'
    elif stem.startswith('Template_'):
        # Template_TechArticle -> Template:TechArticle
        name = stem[len('Template_'):]
        return f'Template:{name}'
    elif suffix == '.css':
        return f'MediaWiki:{stem}.css'
    elif suffix == '.wiki':
        # Non-template .wiki files go to Template: namespace
        return f'Template:{stem}'
    else:
        return stem


def main():
    parser = argparse.ArgumentParser(description='Deploy templates to MediaWiki')
    parser.add_argument('--wiki-url', help='Wiki URL (or WIKI_URL env var)')
    parser.add_argument('--username', '-u', help='Wiki username (or WIKI_USER env var)')
    parser.add_argument('--password', '-p', help='Wiki password (or WIKI_PASSWORD env var)')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Show what would be deployed without deploying')
    args = parser.parse_args()

    wiki_url = args.wiki_url or os.environ.get('WIKI_URL', 'https://wiki.dreamfactory.com')
    username = args.username or os.environ.get('WIKI_USER')
    password = args.password or os.environ.get('WIKI_PASSWORD')

    # Collect template files
    template_files = []
    for tdir in TEMPLATE_DIRS:
        if tdir.exists():
            for f in sorted(tdir.iterdir()):
                if f.suffix in ('.wiki', '.css') and not f.name.startswith('.') and f.name != 'README.md':
                    template_files.append(f)

    if not template_files:
        print('No template files found.')
        return 0

    print(f'Found {len(template_files)} template files to deploy\n')

    if not args.dry_run:
        site = connect_wiki(wiki_url, username, password)
    else:
        site = None

    stats = {'success': 0, 'failed': 0}

    for filepath in template_files:
        page_name = get_page_name(filepath)
        content = filepath.read_text(encoding='utf-8')

        if args.dry_run:
            print(f'  [DRY RUN] {filepath.name} -> {page_name}')
            stats['success'] += 1
            continue

        try:
            page = site.pages[page_name]
            page.save(content, summary='Template sync from GitHub')
            print(f'  OK  {filepath.name} -> {page_name}')
            stats['success'] += 1
        except Exception as e:
            print(f'  FAIL {filepath.name} -> {page_name}: {e}')
            stats['failed'] += 1

    print(f'\nDeployed: {stats["success"]}, Failed: {stats["failed"]}')
    if args.dry_run:
        print('(DRY RUN - no changes made)')

    return 1 if stats['failed'] > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
