#!/usr/bin/env python3
"""
Documentation Migration Inventory Generator

Scans all 3 documentation sources (df-docs, guide, mediawiki) and generates
a comprehensive migration tracking spreadsheet.

Usage:
    python inventory.py [--output migration_inventory.csv]
"""

import os
import re
import csv
import yaml
import argparse
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Base paths (relative to script location)
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
DF_DOCS_PATH = BASE_DIR / "df-docs" / "df-docs" / "docs"
GUIDE_PATH = BASE_DIR / "guide" / "dreamfactory-book-v2" / "content" / "en" / "docs"
MEDIAWIKI_DUMP = BASE_DIR / "mediawiki" / "wiki_dump.sql"


def extract_yaml_frontmatter(content: str) -> Tuple[Dict, str]:
    """Extract YAML frontmatter from markdown content."""
    frontmatter = {}
    body = content

    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
                body = parts[2]
            except yaml.YAMLError:
                pass

    return frontmatter, body


def count_words(text: str) -> int:
    """Count words in text, excluding code blocks."""
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    # Count words
    words = re.findall(r'\b\w+\b', text)
    return len(words)


def count_images(content: str) -> int:
    """Count image references in markdown."""
    # Markdown images: ![alt](path)
    md_images = re.findall(r'!\[.*?\]\(.*?\)', content)
    # HTML images: <img src="...">
    html_images = re.findall(r'<img\s+[^>]*src=', content, re.IGNORECASE)
    return len(md_images) + len(html_images)


def count_links(content: str) -> int:
    """Count internal links in markdown."""
    # Markdown links: [text](path)
    links = re.findall(r'\[.*?\]\([^)]+\)', content)
    return len(links)


def get_target_wiki_page(source_path: str, source_type: str) -> str:
    """Generate target wiki page name from source path."""
    path = Path(source_path)

    # Remove file extension
    name = path.stem
    if name in ('_index', 'index', 'introduction'):
        # Use parent directory name
        name = path.parent.name

    # Convert to wiki page name (Title_Case with underscores)
    name = name.replace('-', '_')
    name = '_'.join(word.capitalize() for word in name.split('_'))

    # Add category prefix based on path
    parts = list(path.parts)
    if 'getting-started' in parts or 'Installing and Configuring DreamFactory' in parts:
        return f"Getting_Started/{name}"
    elif 'Security' in parts or 'security' in parts:
        return f"Security/{name}"
    elif 'api-generation' in parts:
        return f"API_Generation/{name}"
    elif 'system-settings' in parts:
        return f"System_Settings/{name}"
    elif 'admin-settings' in parts:
        return f"Admin_Settings/{name}"
    elif 'AI' in parts:
        return f"AI_Services/{name}"
    elif 'Appendices' in parts:
        return f"Reference/{name}"

    return name


def determine_priority(frontmatter: Dict, path: str) -> str:
    """Determine migration priority based on content type."""
    path_lower = path.lower()

    # P0 - Critical: Main pages and installation
    if 'introduction' in path_lower or 'docker' in path_lower:
        return 'P0-Critical'

    # P1 - High: Getting started and security
    if 'getting-started' in path_lower or 'security' in path_lower:
        return 'P1-High'

    # P2 - Medium: API and system settings
    if 'api-generation' in path_lower or 'system-settings' in path_lower:
        return 'P2-Medium'

    # P3 - Low: Everything else
    return 'P3-Low'


def scan_df_docs() -> List[Dict]:
    """Scan df-docs (Docusaurus) markdown files."""
    items = []

    if not DF_DOCS_PATH.exists():
        print(f"Warning: df-docs path not found: {DF_DOCS_PATH}")
        return items

    for md_file in DF_DOCS_PATH.rglob('*.md'):
        # Skip hidden files and _ai-reference.md (it's 13k+ lines)
        if md_file.name.startswith('.') or md_file.name == '_ai-reference.md':
            continue

        try:
            content = md_file.read_text(encoding='utf-8')
            frontmatter, body = extract_yaml_frontmatter(content)

            rel_path = md_file.relative_to(BASE_DIR)

            items.append({
                'source_path': str(rel_path),
                'source_type': 'df-docs',
                'title': frontmatter.get('title', md_file.stem),
                'target_wiki_page': get_target_wiki_page(str(rel_path), 'df-docs'),
                'priority': determine_priority(frontmatter, str(rel_path)),
                'status': 'Not Started',
                'assigned': '',
                'word_count': count_words(body),
                'images': count_images(content),
                'links': count_links(content),
                'links_verified': 0,
                'difficulty': frontmatter.get('difficulty', ''),
                'keywords': ', '.join(frontmatter.get('keywords', [])) if isinstance(frontmatter.get('keywords'), list) else '',
                'notes': frontmatter.get('description', '')[:200] if frontmatter.get('description') else ''
            })
        except Exception as e:
            print(f"Error processing {md_file}: {e}")

    return items


def scan_guide() -> List[Dict]:
    """Scan guide (Hugo) markdown files."""
    items = []

    if not GUIDE_PATH.exists():
        print(f"Warning: guide path not found: {GUIDE_PATH}")
        return items

    for md_file in GUIDE_PATH.rglob('*.md'):
        if md_file.name.startswith('.'):
            continue

        try:
            content = md_file.read_text(encoding='utf-8')
            frontmatter, body = extract_yaml_frontmatter(content)

            rel_path = md_file.relative_to(BASE_DIR)

            # Check if this content is unique to guide (not in df-docs)
            is_unique = any(x in str(rel_path).lower() for x in [
                'salesforce', 'soap', 'http connector', 'demo',
                'modifying service', 'gdpr', 'architecture faq', 'scalability',
                'configuration parameter'
            ])

            items.append({
                'source_path': str(rel_path),
                'source_type': 'guide',
                'title': frontmatter.get('title', md_file.stem),
                'target_wiki_page': get_target_wiki_page(str(rel_path), 'guide'),
                'priority': 'P3-Low' if not is_unique else 'P2-Medium',
                'status': 'Not Started',
                'assigned': '',
                'word_count': count_words(body),
                'images': count_images(content),
                'links': count_links(content),
                'links_verified': 0,
                'difficulty': '',
                'keywords': '',
                'notes': 'GUIDE-UNIQUE' if is_unique else 'May duplicate df-docs content'
            })
        except Exception as e:
            print(f"Error processing {md_file}: {e}")

    return items


def parse_mediawiki_dump() -> List[Dict]:
    """Parse MediaWiki SQL dump to extract page information."""
    items = []

    if not MEDIAWIKI_DUMP.exists():
        print(f"Warning: MediaWiki dump not found: {MEDIAWIKI_DUMP}")
        return items

    print("Parsing MediaWiki dump (this may take a moment)...")

    # Read the SQL dump and extract INSERT statements for the page table
    try:
        with open(MEDIAWIKI_DUMP, 'r', encoding='utf-8', errors='replace') as f:
            in_page_insert = False
            page_data = []

            for line in f:
                # Look for INSERT INTO `page` statements
                if 'INSERT INTO `page`' in line:
                    in_page_insert = True
                    # Extract values from this line
                    matches = re.findall(r'\((\d+),(\d+),\'([^\']*)\',', line)
                    for match in matches:
                        page_id, namespace, title = match
                        # Only include main namespace (0) pages
                        if namespace == '0' and title and not title.startswith('MediaWiki:'):
                            page_data.append({
                                'page_id': page_id,
                                'title': title.replace('_', ' ')
                            })
                elif in_page_insert and line.strip().endswith(';'):
                    in_page_insert = False

        # Create inventory items from parsed pages
        for page in page_data[:500]:  # Limit to first 500 for performance
            # Determine version namespace based on content/date (simplified)
            target_namespace = 'Legacy'  # Default to Legacy for existing wiki content

            items.append({
                'source_path': f"mediawiki:page_id={page['page_id']}",
                'source_type': 'mediawiki',
                'title': page['title'],
                'target_wiki_page': f"{target_namespace}:{page['title'].replace(' ', '_')}",
                'priority': 'P3-Low',
                'status': 'Not Started',
                'assigned': '',
                'word_count': 0,  # Would need to parse text table for accurate count
                'images': 0,
                'links': 0,
                'links_verified': 0,
                'difficulty': '',
                'keywords': '',
                'notes': 'Legacy wiki content - needs version classification'
            })

    except Exception as e:
        print(f"Error parsing MediaWiki dump: {e}")

    return items


def generate_inventory(output_file: str):
    """Generate the complete migration inventory."""
    all_items = []

    print("Scanning df-docs (Docusaurus)...")
    all_items.extend(scan_df_docs())
    print(f"  Found {len([i for i in all_items if i['source_type'] == 'df-docs'])} files")

    print("Scanning guide (Hugo)...")
    all_items.extend(scan_guide())
    print(f"  Found {len([i for i in all_items if i['source_type'] == 'guide'])} files")

    print("Parsing MediaWiki dump...")
    all_items.extend(parse_mediawiki_dump())
    print(f"  Found {len([i for i in all_items if i['source_type'] == 'mediawiki'])} pages")

    # Sort by priority then source type
    priority_order = {'P0-Critical': 0, 'P1-High': 1, 'P2-Medium': 2, 'P3-Low': 3}
    all_items.sort(key=lambda x: (priority_order.get(x['priority'], 99), x['source_type']))

    # Write CSV
    fieldnames = [
        'source_path', 'source_type', 'title', 'target_wiki_page', 'priority',
        'status', 'assigned', 'word_count', 'images', 'links', 'links_verified',
        'difficulty', 'keywords', 'notes'
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_items)

    print(f"\nInventory generated: {output_file}")
    print(f"Total items: {len(all_items)}")
    print(f"  - df-docs: {len([i for i in all_items if i['source_type'] == 'df-docs'])}")
    print(f"  - guide: {len([i for i in all_items if i['source_type'] == 'guide'])}")
    print(f"  - mediawiki: {len([i for i in all_items if i['source_type'] == 'mediawiki'])}")

    # Print priority breakdown
    print("\nPriority breakdown:")
    for priority in ['P0-Critical', 'P1-High', 'P2-Medium', 'P3-Low']:
        count = len([i for i in all_items if i['priority'] == priority])
        print(f"  {priority}: {count}")


def main():
    parser = argparse.ArgumentParser(description='Generate documentation migration inventory')
    parser.add_argument('--output', '-o', default='migration_inventory.csv',
                        help='Output CSV file path')
    args = parser.parse_args()

    output_path = SCRIPT_DIR / args.output
    generate_inventory(str(output_path))


if __name__ == '__main__':
    main()
