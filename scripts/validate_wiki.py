#!/usr/bin/env python3
"""
Wiki content validation for CI/CD quality gate.

Checks run on every PR to catch issues before they hit the live wiki:
  1. Internal link validation — every [[Page_Name]] resolves to a real page
  2. Redirect target validation — every #REDIRECT [[Target]] points to a real page
  3. page_map.json consistency — valid JSON, no duplicate values
  4. Frontmatter validation — title and description present for WikiSEO injection

Usage:
    python validate_wiki.py --docs ../docs/
    python validate_wiki.py --docs ../docs/ --format json
    python validate_wiki.py --docs ../docs/ --strict  # fail on warnings too

Exit codes:
    0 = all checks pass
    1 = errors found (blocks merge)
    2 = warnings only (--strict makes these errors)
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ---------------------------------------------------------------------------
# Import helpers from sibling scripts
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from inventory import extract_yaml_frontmatter  # noqa: E402


# ---------------------------------------------------------------------------
# Page name resolution (mirrors sync_to_wiki.py logic exactly)
# ---------------------------------------------------------------------------

def load_page_map(docs_dir: Path) -> Dict[str, str]:
    """Load page_map.json from docs directory."""
    pm_path = docs_dir / "page_map.json"
    if pm_path.exists():
        with open(pm_path) as f:
            return json.load(f)
    return {}


def load_inventory_map(scripts_dir: Path) -> Dict[str, str]:
    """Load migration_inventory.csv target_wiki_page mappings."""
    inv_path = scripts_dir / "migration_inventory.csv"
    mapping = {}
    if inv_path.exists():
        with open(inv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                src = row.get("source_path", "")
                target = row.get("target_wiki_page", "")
                if src and target:
                    # inventory stores paths relative to project root, strip prefix
                    for prefix in ["df-docs/df-docs/docs/", "guide/dreamfactory-book-v2/content/en/docs/"]:
                        if src.startswith(prefix):
                            src = src[len(prefix):]
                    mapping[src] = target
    return mapping


def auto_generate_page_name(rel_path: str) -> str:
    """Auto-generate wiki page name from file path (mirrors sync_to_wiki.py)."""
    name = str(Path(rel_path).with_suffix(''))
    parts = name.split('/')
    wiki_name = '/'.join(
        '_'.join(word.capitalize() for word in part.replace('-', '_').split('_'))
        for part in parts
    )
    return wiki_name


def resolve_page_name(rel_path: str, page_map: Dict, inventory_map: Dict) -> str:
    """Resolve a .wiki file path to its wiki page name using the same
    lookup order as sync_to_wiki.py: inventory → page_map → auto-generate."""
    if rel_path in inventory_map:
        return inventory_map[rel_path]
    if rel_path in page_map:
        return page_map[rel_path]
    return auto_generate_page_name(rel_path)


# ---------------------------------------------------------------------------
# Build the set of all known page names
# ---------------------------------------------------------------------------

def build_page_name_set(docs_dir: Path, page_map: Dict, inventory_map: Dict) -> Set[str]:
    """Build set of all wiki page names that will exist after deployment."""
    pages = set()

    # 1. All .wiki files in docs/ resolved through the naming pipeline
    for wiki_file in docs_dir.rglob("*.wiki"):
        rel = str(wiki_file.relative_to(docs_dir))
        name = resolve_page_name(rel, page_map, inventory_map)
        pages.add(name)

    # 2. All inventory target names (these are the canonical page names
    #    from the migration — redirects reference these)
    for target in inventory_map.values():
        if target:
            pages.add(target)

    # 3. All page_map target names
    for target in page_map.values():
        if target:
            pages.add(target)

    return pages


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------

class Issue:
    def __init__(self, level: str, file: str, line: int, check: str, message: str):
        self.level = level  # "error" or "warning"
        self.file = file
        self.line = line
        self.check = check
        self.message = message

    def __str__(self):
        prefix = "ERROR" if self.level == "error" else "WARN "
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"  {prefix}  [{self.check}] {loc}: {self.message}"

    def to_dict(self):
        return {
            "level": self.level,
            "file": self.file,
            "line": self.line,
            "check": self.check,
            "message": self.message,
        }


def _normalize_page_name(name: str) -> str:
    """Normalize a page name the way MediaWiki does: spaces → underscores."""
    return name.replace(' ', '_')


def check_internal_links(docs_dir: Path, known_pages: Set[str]) -> List[Issue]:
    """Check that all [[Page_Name]] links point to pages that exist."""
    issues = []
    # Build normalized lookup (MediaWiki treats spaces and underscores as equivalent)
    pages_normalized = {_normalize_page_name(p) for p in known_pages}
    # Also build a case-insensitive lookup for near-miss detection
    pages_lower = {_normalize_page_name(p).lower(): p for p in known_pages}

    # MediaWiki built-in namespaces and special pages we should skip
    skip_prefixes = {
        "Category:", "File:", "Image:", "Media:", "Special:",
        "Template:", "Help:", "Talk:", "User:", "Wikipedia:",
        "MediaWiki:", ":Category:", ":File:",
    }

    for wiki_file in sorted(docs_dir.rglob("*.wiki")):
        rel = str(wiki_file.relative_to(docs_dir))
        content = wiki_file.read_text(errors="replace")

        # Skip redirect stubs — they only have #REDIRECT, checked separately
        if content.strip().startswith("#REDIRECT"):
            continue

        for line_num, line in enumerate(content.splitlines(), 1):
            # Match [[Target]] and [[Target|Display text]]
            for match in re.finditer(r'\[\[([^\]|#]+)(?:[|#][^\]]*?)?\]\]', line):
                target = match.group(1).strip()

                # Skip namespace-prefixed links
                if any(target.startswith(p) for p in skip_prefixes):
                    continue

                # Skip external-style links
                if target.startswith("http://") or target.startswith("https://"):
                    continue

                # Skip Docusaurus-style relative paths (not valid MediaWiki links)
                if target.startswith("../") or target.startswith("./"):
                    continue

                # Skip file paths (images, docs/ prefix — Docusaurus artifacts)
                if target.startswith("docs/") or target.startswith("img/"):
                    continue

                # Skip things that look like code, not wiki links
                if target.startswith("'") or target.startswith('"'):
                    continue

                normalized = _normalize_page_name(target)
                if normalized not in pages_normalized:
                    # Check case-insensitive match
                    if normalized.lower() in pages_lower:
                        suggestion = pages_lower[normalized.lower()]
                        issues.append(Issue(
                            "warning", rel, line_num, "internal-link",
                            f"[[{target}]] — case mismatch, did you mean [[{suggestion}]]?"
                        ))
                    else:
                        issues.append(Issue(
                            "error", rel, line_num, "internal-link",
                            f"[[{target}]] — page does not exist"
                        ))

    return issues


def check_redirects(docs_dir: Path, known_pages: Set[str]) -> List[Issue]:
    """Check that all #REDIRECT [[Target]] stubs point to real pages."""
    issues = []
    pages_normalized = {_normalize_page_name(p) for p in known_pages}
    redirect_dir = docs_dir / "redirects"
    if not redirect_dir.exists():
        return issues

    for wiki_file in sorted(redirect_dir.rglob("*.wiki")):
        rel = str(wiki_file.relative_to(docs_dir))
        content = wiki_file.read_text(errors="replace").strip()

        if not content.startswith("#REDIRECT"):
            # Hub page living in redirects/ — not a redirect, skip
            continue

        match = re.search(r'#REDIRECT\s*\[\[([^\]]+)\]\]', content)
        if not match:
            issues.append(Issue(
                "error", rel, 1, "redirect",
                "Malformed #REDIRECT — could not parse target"
            ))
            continue

        target = match.group(1).strip()
        normalized = _normalize_page_name(target)
        if normalized not in pages_normalized:
            issues.append(Issue(
                "error", rel, 1, "redirect",
                f"#REDIRECT [[{target}]] — target page does not exist"
            ))

    return issues


def check_page_map(docs_dir: Path) -> List[Issue]:
    """Validate page_map.json structure and consistency."""
    issues = []
    pm_path = docs_dir / "page_map.json"

    if not pm_path.exists():
        issues.append(Issue("warning", "page_map.json", 0, "page-map", "page_map.json not found"))
        return issues

    try:
        with open(pm_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        issues.append(Issue("error", "page_map.json", 0, "page-map", f"Invalid JSON: {e}"))
        return issues

    if not isinstance(data, dict):
        issues.append(Issue("error", "page_map.json", 0, "page-map", "Expected a JSON object"))
        return issues

    # Check for duplicate target page names
    seen_targets = {}
    for file_key, page_name in data.items():
        if page_name in seen_targets:
            issues.append(Issue(
                "error", "page_map.json", 0, "page-map",
                f"Duplicate target '{page_name}' — used by both '{seen_targets[page_name]}' and '{file_key}'"
            ))
        else:
            seen_targets[page_name] = file_key

        # Check that source file exists (skip redirects that may be generated)
        source_path = docs_dir / file_key
        if not source_path.exists():
            issues.append(Issue(
                "warning", "page_map.json", 0, "page-map",
                f"'{file_key}' mapped but file does not exist in docs/"
            ))

    return issues


def check_frontmatter(docs_dir: Path) -> List[Issue]:
    """Check that content pages have title and description for WikiSEO."""
    issues = []

    for wiki_file in sorted(docs_dir.rglob("*.wiki")):
        rel = str(wiki_file.relative_to(docs_dir))

        # Skip redirects
        if "redirects/" in rel:
            continue

        content = wiki_file.read_text(errors="replace")

        # Skip redirect stubs that aren't in the redirects dir
        if content.strip().startswith("#REDIRECT"):
            continue

        frontmatter, _ = extract_yaml_frontmatter(content)

        if not frontmatter.get("title"):
            issues.append(Issue(
                "warning", rel, 0, "frontmatter",
                "Missing 'title' in frontmatter — WikiSEO will skip this page"
            ))

        if not frontmatter.get("description"):
            issues.append(Issue(
                "warning", rel, 0, "frontmatter",
                "Missing 'description' in frontmatter — no meta description for SEO"
            ))

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Validate wiki content for CI/CD")
    parser.add_argument("--docs", required=True, help="Path to docs/ directory")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args()

    docs_dir = Path(args.docs).resolve()
    scripts_dir = Path(__file__).resolve().parent

    if not docs_dir.exists():
        print(f"Error: docs directory not found: {docs_dir}", file=sys.stderr)
        sys.exit(1)

    # Load mappings
    page_map = load_page_map(docs_dir)
    inventory_map = load_inventory_map(scripts_dir)
    known_pages = build_page_name_set(docs_dir, page_map, inventory_map)

    # Run all checks
    all_issues: List[Issue] = []
    all_issues.extend(check_page_map(docs_dir))
    all_issues.extend(check_redirects(docs_dir, known_pages))
    all_issues.extend(check_internal_links(docs_dir, known_pages))
    all_issues.extend(check_frontmatter(docs_dir))

    errors = [i for i in all_issues if i.level == "error"]
    warnings = [i for i in all_issues if i.level == "warning"]

    if args.format == "json":
        output = {
            "summary": {
                "errors": len(errors),
                "warnings": len(warnings),
                "total_pages": len(known_pages),
            },
            "issues": [i.to_dict() for i in all_issues],
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\nWiki Validation Report")
        print(f"{'=' * 60}")
        print(f"  Pages scanned: {len(known_pages)}")
        print(f"  Errors:        {len(errors)}")
        print(f"  Warnings:      {len(warnings)}")
        print(f"{'=' * 60}")

        if errors:
            print(f"\nERRORS ({len(errors)}):")
            for issue in errors:
                print(str(issue))

        if warnings:
            print(f"\nWARNINGS ({len(warnings)}):")
            for issue in warnings:
                print(str(issue))

        if not errors and not warnings:
            print("\n  All checks passed.")

    # Exit code
    if errors:
        sys.exit(1)
    elif warnings and args.strict:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
