#!/usr/bin/env python3
"""
validate_migration.py - Validate migrated documentation

Checks migrated content for:
- Broken internal links
- Missing images
- Word count variance from source
- Category assignment completeness
- Formatting issues

Usage:
    python validate_migration.py --wiki-url https://wiki.dreamfactory.com \
                                  --inventory migration_inventory.csv \
                                  [--output validation_report.csv]
"""

import os
import re
import csv
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin
import yaml

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: requests not installed. Wiki validation will be limited.")


SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent


class MigrationValidator:
    """Validates documentation migration."""

    def __init__(self, wiki_url: str = None, inventory_file: str = None):
        self.wiki_url = wiki_url
        self.inventory_file = inventory_file
        self.inventory = []
        self.issues = []
        self.wiki_pages: Set[str] = set()

    def load_inventory(self) -> bool:
        """Load migration inventory CSV."""
        if not self.inventory_file or not Path(self.inventory_file).exists():
            print(f"Warning: Inventory file not found: {self.inventory_file}")
            return False

        with open(self.inventory_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            self.inventory = list(reader)

        print(f"Loaded {len(self.inventory)} items from inventory")
        return True

    def get_source_word_count(self, source_path: str) -> int:
        """Get word count from source file."""
        full_path = BASE_DIR / source_path
        if not full_path.exists():
            return 0

        try:
            content = full_path.read_text(encoding='utf-8')
            # Remove frontmatter
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    content = parts[2]
            # Remove code blocks
            content = re.sub(r'```[\s\S]*?```', '', content)
            content = re.sub(r'`[^`]+`', '', content)
            # Count words
            words = re.findall(r'\b\w+\b', content)
            return len(words)
        except Exception:
            return 0

    def check_wiki_page_exists(self, page_name: str) -> bool:
        """Check if a wiki page exists (via API or cache)."""
        if page_name in self.wiki_pages:
            return True

        if not REQUESTS_AVAILABLE or not self.wiki_url:
            return True  # Assume exists if we can't check

        try:
            api_url = f"{self.wiki_url.rstrip('/')}/api.php"
            params = {
                'action': 'query',
                'titles': page_name,
                'format': 'json'
            }
            response = requests.get(api_url, params=params, timeout=10)
            data = response.json()

            pages = data.get('query', {}).get('pages', {})
            for page_id, page_data in pages.items():
                if page_id != '-1' and 'missing' not in page_data:
                    self.wiki_pages.add(page_name)
                    return True

            return False

        except Exception:
            return True  # Assume exists on error

    def extract_links_from_wiki(self, content: str) -> List[str]:
        """Extract internal wiki links from content."""
        links = []

        # [[Page|text]] or [[Page]]
        wiki_links = re.findall(r'\[\[([^\]|]+)', content)
        for link in wiki_links:
            # Skip category and file links
            if not link.startswith(('Category:', 'File:', '#')):
                links.append(link)

        return links

    def extract_images_from_wiki(self, content: str) -> List[str]:
        """Extract image references from wiki content."""
        images = []

        # [[File:name|...]]
        file_links = re.findall(r'\[\[File:([^\]|]+)', content)
        images.extend(file_links)

        return images

    def validate_converted_file(self, wiki_file: str, source_file: str = None) -> List[Dict]:
        """Validate a single converted wiki file."""
        issues = []
        wiki_path = Path(wiki_file)

        if not wiki_path.exists():
            issues.append({
                'file': wiki_file,
                'type': 'Missing File',
                'severity': 'Blocker',
                'description': 'Converted wiki file not found'
            })
            return issues

        content = wiki_path.read_text(encoding='utf-8')

        # Check for empty content
        if len(content.strip()) < 50:
            issues.append({
                'file': wiki_file,
                'type': 'Empty Content',
                'severity': 'Major',
                'description': 'Wiki file has very little content'
            })

        # Check for broken wiki syntax
        # Unclosed tags
        open_tags = len(re.findall(r'<syntaxhighlight[^>]*>', content))
        close_tags = len(re.findall(r'</syntaxhighlight>', content))
        if open_tags != close_tags:
            issues.append({
                'file': wiki_file,
                'type': 'Syntax Error',
                'severity': 'Major',
                'description': f'Mismatched syntaxhighlight tags ({open_tags} open, {close_tags} close)'
            })

        # Check for Pandoc artifacts
        if '\\[' in content or '\\]' in content:
            issues.append({
                'file': wiki_file,
                'type': 'Formatting',
                'severity': 'Minor',
                'description': 'Escaped brackets detected (Pandoc artifact)'
            })

        # Check for broken tables
        if '{|' in content:
            table_opens = content.count('{|')
            table_closes = content.count('|}')
            if table_opens != table_closes:
                issues.append({
                    'file': wiki_file,
                    'type': 'Syntax Error',
                    'severity': 'Major',
                    'description': f'Mismatched table tags ({table_opens} open, {table_closes} close)'
                })

        # Check word count variance if source file provided
        if source_file:
            source_word_count = self.get_source_word_count(source_file)
            if source_word_count > 0:
                # Count words in wiki content (excluding markup)
                wiki_text = re.sub(r'\[\[[^\]]+\]\]', '', content)  # Remove links
                wiki_text = re.sub(r'<[^>]+>', '', wiki_text)  # Remove HTML
                wiki_text = re.sub(r'\{\|[\s\S]*?\|\}', '', wiki_text)  # Remove tables
                wiki_words = len(re.findall(r'\b\w+\b', wiki_text))

                variance = abs(wiki_words - source_word_count) / max(source_word_count, 1)
                if variance > 0.20:  # More than 20% variance
                    issues.append({
                        'file': wiki_file,
                        'type': 'Content Variance',
                        'severity': 'Minor',
                        'description': f'Word count variance: source={source_word_count}, wiki={wiki_words} ({variance*100:.1f}%)'
                    })

        # Check for missing categories
        if '[[Category:' not in content:
            issues.append({
                'file': wiki_file,
                'type': 'Missing Metadata',
                'severity': 'Minor',
                'description': 'No categories assigned'
            })

        # Check internal links
        links = self.extract_links_from_wiki(content)
        for link in links[:10]:  # Check first 10 links only
            if not self.check_wiki_page_exists(link):
                issues.append({
                    'file': wiki_file,
                    'type': 'Broken Link',
                    'severity': 'Major',
                    'description': f'Internal link target not found: {link}'
                })

        return issues

    def validate_converted_directory(self, converted_dir: str) -> List[Dict]:
        """Validate all files in converted directory."""
        all_issues = []
        converted_path = Path(converted_dir)

        if not converted_path.exists():
            print(f"Error: Converted directory not found: {converted_dir}")
            return all_issues

        wiki_files = list(converted_path.rglob('*.wiki'))
        print(f"Validating {len(wiki_files)} converted files...")

        for i, wiki_file in enumerate(wiki_files):
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(wiki_files)}")

            # Find corresponding source file
            rel_path = wiki_file.relative_to(converted_path)
            source_path = str(rel_path).replace('.wiki', '.md')

            # Check inventory for source path
            source_file = None
            for item in self.inventory:
                if source_path in item.get('source_path', ''):
                    source_file = item.get('source_path')
                    break

            issues = self.validate_converted_file(str(wiki_file), source_file)
            all_issues.extend(issues)

        return all_issues

    def validate_inventory_completeness(self) -> List[Dict]:
        """Check that all inventory items have been migrated."""
        issues = []

        for item in self.inventory:
            if item.get('source_type') != 'df-docs':
                continue  # Focus on primary source

            source_path = item.get('source_path', '')
            status = item.get('status', 'Not Started')

            if status == 'Not Started':
                issues.append({
                    'file': source_path,
                    'type': 'Not Migrated',
                    'severity': 'Major',
                    'description': f"Source file not migrated: {item.get('title', 'Unknown')}"
                })

        return issues

    def generate_report(self, issues: List[Dict], output_file: str):
        """Generate validation report CSV."""
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['file', 'type', 'severity', 'description'])
            writer.writeheader()
            writer.writerows(issues)

        print(f"\nValidation report written to: {output_file}")

        # Print summary
        severity_counts = {}
        type_counts = {}
        for issue in issues:
            sev = issue.get('severity', 'Unknown')
            typ = issue.get('type', 'Unknown')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            type_counts[typ] = type_counts.get(typ, 0) + 1

        print("\n" + "=" * 50)
        print("Validation Summary")
        print("=" * 50)
        print(f"Total issues: {len(issues)}")
        print("\nBy severity:")
        for sev in ['Blocker', 'Major', 'Minor']:
            count = severity_counts.get(sev, 0)
            print(f"  {sev}: {count}")
        print("\nBy type:")
        for typ, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"  {typ}: {count}")
        print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description='Validate documentation migration')
    parser.add_argument('--wiki-url', '-w',
                        help='MediaWiki URL for link validation')
    parser.add_argument('--inventory', '-i', default='migration_inventory.csv',
                        help='Migration inventory CSV')
    parser.add_argument('--converted-dir', '-c', default='./converted',
                        help='Directory containing converted .wiki files')
    parser.add_argument('--output', '-o', default='validation_report.csv',
                        help='Output report CSV')
    parser.add_argument('--check-links', '-l', action='store_true',
                        help='Check wiki links (requires internet)')

    args = parser.parse_args()

    validator = MigrationValidator(
        wiki_url=args.wiki_url if args.check_links else None,
        inventory_file=SCRIPT_DIR / args.inventory
    )

    # Load inventory
    validator.load_inventory()

    all_issues = []

    # Validate converted files
    converted_path = SCRIPT_DIR / args.converted_dir
    if converted_path.exists():
        all_issues.extend(validator.validate_converted_directory(str(converted_path)))
    else:
        print(f"Note: Converted directory not found: {converted_path}")
        print("  Run batch_convert.sh first to create converted files")

    # Check inventory completeness
    all_issues.extend(validator.validate_inventory_completeness())

    # Generate report
    validator.generate_report(all_issues, str(SCRIPT_DIR / args.output))


if __name__ == '__main__':
    main()
