#!/usr/bin/env python3
"""
Content scoring engine for wiki migration documentation.

Evaluates .md and .wiki files against 7 weighted SEO/content quality criteria
defined in guidance.md. Produces per-file scores and actionable fix recommendations.

Pipeline position:
    inventory.py → batch_convert.sh → postprocess.py → content_score.py → upload_to_wiki.py

Usage:
    # Single file
    python content_score.py --file path/to/page.wiki
    python content_score.py --file path/to/page.md --format json

    # Batch directory
    python content_score.py --dir path/to/docs/ --output report.csv

    # CI gating
    python content_score.py --dir path/ --output report.csv --threshold 70
"""

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Import helpers from sibling scripts
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from inventory import extract_yaml_frontmatter  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# (compiled_regex, fix_message) — order doesn't matter; all are scanned.
OUTDATED_VERSION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Ubuntu
    (re.compile(r'\bUbuntu\s+1[2-9]\.\d+', re.IGNORECASE),
     'Update to Ubuntu 24.04 LTS'),
    (re.compile(r'\bUbuntu\s+2[0-2]\.\d+', re.IGNORECASE),
     'Update to Ubuntu 24.04 LTS'),
    # CentOS
    (re.compile(r'\bCentOS\s+[5-7]\b', re.IGNORECASE),
     'CentOS 5-7 are EOL; use AlmaLinux 9 or Ubuntu 24.04'),
    # Debian old releases
    (re.compile(r'\bDebian\s+(jessie|stretch|buster)\b', re.IGNORECASE),
     'Update to Debian 12 (bookworm)'),
    # macOS / OS X legacy
    (re.compile(r'\bmacOS\s+10\.\d+', re.IGNORECASE),
     'Update to macOS 14+ (Sonoma)'),
    (re.compile(r'\bOS\s+X\b'),
     'Replace "OS X" with "macOS 14+"'),
    # PHP
    (re.compile(r'\bPHP\s+[5-7]\.\d+', re.IGNORECASE),
     'Update to PHP 8.1+'),
    (re.compile(r'\bPHP\s+8\.0\b', re.IGNORECASE),
     'Update to PHP 8.1+ (8.0 is EOL)'),
    # MySQL
    (re.compile(r'\bMySQL\s+5\.\d+', re.IGNORECASE),
     'Update to MySQL 8.0+'),
    # DreamFactory old major versions
    (re.compile(r'\bDreamFactory\s+[2-6]\.\d+', re.IGNORECASE),
     'Update to DreamFactory 7.4.x'),
    (re.compile(r'\bDreamFactory\s+7\.[0-3]\b', re.IGNORECASE),
     'Update to DreamFactory 7.4.x'),
    # Old API versions
    (re.compile(r'\bapi/v1\b'),
     'Update to api/v2 endpoint'),
    # Windows Server
    (re.compile(r'\bWindows\s+Server\s+20(08|12|16)\b', re.IGNORECASE),
     'Update to Windows Server 2022'),
    # Apache old versions
    (re.compile(r'\bApache\s+2\.[0-2]\b', re.IGNORECASE),
     'Update to Apache 2.4+'),
    # nginx old versions
    (re.compile(r'\bnginx\s+1\.[0-9]\b', re.IGNORECASE),
     'Update to nginx 1.24+'),
    (re.compile(r'\bnginx\s+1\.1\d\b', re.IGNORECASE),
     'Update to nginx 1.24+'),
]

# Lines containing these phrases get a pass — they're discussing upgrades.
UPGRADE_CONTEXT_PATTERNS: List[re.Pattern] = [
    re.compile(r'upgrad(e|ing)\s+from', re.IGNORECASE),
    re.compile(r'migrat(e|ing)\s+from', re.IGNORECASE),
    re.compile(r'\blegacy\b', re.IGNORECASE),
    re.compile(r'\bdeprecated\b', re.IGNORECASE),
    re.compile(r'\bpreviously\b', re.IGNORECASE),
    re.compile(r'\bold(er)?\s+version', re.IGNORECASE),
    re.compile(r'\bno\s+longer\s+supported\b', re.IGNORECASE),
    re.compile(r'\bend[\s-]of[\s-]life\b', re.IGNORECASE),
]

# Severity labels for output
SEVERITY_CRITICAL = 'CRITICAL'
SEVERITY_WARNING = 'WARNING'
SEVERITY_INFO = 'INFO'

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CriterionResult:
    """Result for a single scoring criterion."""
    name: str
    score: float
    max_score: float
    passed: bool
    severity: str  # CRITICAL, WARNING, INFO
    detail: str
    fix: str = ''
    lines: List[int] = field(default_factory=list)

    @property
    def pct(self) -> float:
        return (self.score / self.max_score * 100) if self.max_score else 0


@dataclass
class ContentScore:
    """Complete score for a single file."""
    file_path: str
    format: str  # 'md' or 'wiki'
    overall_score: float
    criteria: List[CriterionResult]
    word_count: int
    is_stub: bool
    is_hub: bool

    def to_dict(self) -> dict:
        d = asdict(self)
        d['criteria'] = [asdict(c) for c in self.criteria]
        return d


# ---------------------------------------------------------------------------
# ContentScorer
# ---------------------------------------------------------------------------

class ContentScorer:
    """Scores a single documentation file against 7 quality criteria."""

    def __init__(self, inventory_path: Optional[str] = None):
        self._inventory_path = inventory_path or str(
            _SCRIPTS_DIR / 'migration_inventory.csv'
        )
        self._link_mapping: Optional[Dict[str, str]] = None
        self._inventory_rows: Optional[List[Dict[str, str]]] = None
        self._inventory_targets: Optional[set] = None

    # -- lazy loaders -------------------------------------------------------

    def _get_link_mapping(self) -> Dict[str, str]:
        if self._link_mapping is None:
            self._link_mapping = self._load_link_mapping()
        return self._link_mapping

    def _load_link_mapping(self) -> Dict[str, str]:
        """Mirrors postprocess._load_link_mapping() without importing it."""
        mapping: Dict[str, str] = {}
        inv = Path(self._inventory_path)
        if not inv.exists():
            return mapping
        with open(inv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                source = row.get('source_path', '')
                target = row.get('target_wiki_page', '')
                if not source or not target:
                    continue
                for prefix in [
                    'df-docs/df-docs/docs/',
                    'guide/dreamfactory-book-v2/content/en/docs/',
                ]:
                    if source.startswith(prefix):
                        source = source[len(prefix):]
                        break
                source_no_ext = re.sub(r'\.md$', '', source)
                mapping[source_no_ext.lower()] = target
                slug = Path(source_no_ext).stem
                if slug and slug != '_index' and slug not in mapping:
                    mapping[slug.lower()] = target
                mapping[('docs/' + source_no_ext).lower()] = target
        return mapping

    def _get_inventory_rows(self) -> List[Dict[str, str]]:
        if self._inventory_rows is None:
            self._inventory_rows = []
            inv = Path(self._inventory_path)
            if inv.exists():
                with open(inv, 'r', encoding='utf-8') as f:
                    self._inventory_rows = list(csv.DictReader(f))
        return self._inventory_rows

    def _get_inventory_targets(self) -> set:
        if self._inventory_targets is None:
            self._inventory_targets = {
                row.get('target_wiki_page', '')
                for row in self._get_inventory_rows()
                if row.get('target_wiki_page')
            }
        return self._inventory_targets

    # -- format detection ---------------------------------------------------

    @staticmethod
    def detect_format(path: str) -> str:
        ext = Path(path).suffix.lower()
        if ext == '.wiki':
            return 'wiki'
        return 'md'

    # -- main scoring entry point -------------------------------------------

    def score_file(self, path: str) -> ContentScore:
        """Score a single file against all 7 criteria."""
        path = str(Path(path).resolve())
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        fmt = self.detect_format(path)
        frontmatter: Dict = {}
        body = content

        if fmt == 'md':
            frontmatter, body = extract_yaml_frontmatter(content)

        word_count = self._count_words_inclusive(content, fmt)
        internal_links = (
            self._extract_internal_links_wiki(content)
            if fmt == 'wiki'
            else self._extract_internal_links_md(body)
        )
        is_hub = self._is_hub_page(path, internal_links)

        criteria = [
            self._score_word_count(word_count),
            self._score_version_currency(content),
            self._score_crosslinks(internal_links, is_hub),
            self._score_url_structure(path),
            self._score_structured_data(content),
            self._score_code_examples(content, fmt),
            self._score_categories(content, fmt, frontmatter),
        ]

        overall = sum(c.score for c in criteria)
        is_stub = word_count < 100

        return ContentScore(
            file_path=path,
            format=fmt,
            overall_score=round(overall, 1),
            criteria=criteria,
            word_count=word_count,
            is_stub=is_stub,
            is_hub=is_hub,
        )

    # -- word counting (includes code blocks, unlike inventory.py) ----------

    @staticmethod
    def _count_words_inclusive(content: str, fmt: str) -> int:
        """Count words including code block content."""
        text = content
        # Strip frontmatter for md
        if fmt == 'md' and text.startswith('---'):
            parts = text.split('---', 2)
            if len(parts) >= 3:
                text = parts[2]
        # Strip wiki markup noise but keep words inside
        if fmt == 'wiki':
            text = re.sub(r'\[\[Category:[^\]]*\]\]', '', text)
            text = re.sub(r'<syntaxhighlight[^>]*>', '', text)
            text = re.sub(r'</syntaxhighlight>', '', text)
            text = re.sub(r'\{\|[\s\S]*?\|\}', '', text)  # wiki tables
        # Strip HTML tags but keep text content
        text = re.sub(r'<[^>]+>', ' ', text)
        # Strip MediaWiki link markup, keeping display text
        text = re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', text)
        # Strip markdown image syntax
        text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
        words = re.findall(r'\b\w+\b', text)
        return len(words)

    # -- criterion scorers --------------------------------------------------

    def _score_word_count(self, word_count: int) -> CriterionResult:
        max_score = 20
        if word_count >= 500:
            score = max_score
            detail = f'{word_count} words (meets 500-word minimum)'
            fix = ''
            severity = SEVERITY_INFO
        elif word_count < 100:
            score = round(max_score * (word_count / 500), 1)
            detail = f'{word_count} words — STUB (< 100 words)'
            fix = f'Expand content to at least 500 words ({500 - word_count} more needed) or merge into a parent page'
            severity = SEVERITY_CRITICAL
        else:
            score = round(max_score * (word_count / 500), 1)
            detail = f'{word_count} words — needs {500 - word_count} more for minimum'
            fix = f'Add {500 - word_count} more words of substantive content'
            severity = SEVERITY_WARNING
        return CriterionResult(
            name='Word Count',
            score=min(score, max_score),
            max_score=max_score,
            passed=word_count >= 500,
            severity=severity,
            detail=detail,
            fix=fix,
        )

    def _score_version_currency(self, content: str) -> CriterionResult:
        max_score = 20
        lines = content.splitlines()
        issues: List[Tuple[int, str, str]] = []  # (line_no, match, fix)

        for line_no, line in enumerate(lines, 1):
            # Skip upgrade-context lines
            if any(p.search(line) for p in UPGRADE_CONTEXT_PATTERNS):
                continue
            for pattern, fix_msg in OUTDATED_VERSION_PATTERNS:
                match = pattern.search(line)
                if match:
                    issues.append((line_no, match.group(), fix_msg))

        if not issues:
            return CriterionResult(
                name='Version Currency',
                score=max_score,
                max_score=max_score,
                passed=True,
                severity=SEVERITY_INFO,
                detail='No outdated version references found',
            )

        # Deduct proportionally: each issue costs up to 4 points, capped at 0
        penalty = min(len(issues) * 4, max_score)
        score = max(max_score - penalty, 0)
        detail_parts = [f'Line {ln}: "{m}" → {f}' for ln, m, f in issues]
        return CriterionResult(
            name='Version Currency',
            score=score,
            max_score=max_score,
            passed=len(issues) == 0,
            severity=SEVERITY_CRITICAL,
            detail=f'{len(issues)} outdated reference(s) found',
            fix='; '.join(detail_parts),
            lines=[ln for ln, _, _ in issues],
        )

    def _score_crosslinks(
        self, internal_links: List[str], is_hub: bool
    ) -> CriterionResult:
        max_score = 15
        n = len(internal_links)

        if is_hub:
            threshold = 25
            if n >= threshold:
                score = max_score
                passed = True
                detail = f'{n} internal links (hub page; threshold: {threshold})'
                fix = ''
                severity = SEVERITY_INFO
            else:
                score = round(max_score * min(n / threshold, 1.0), 1)
                passed = False
                detail = f'{n} internal links (hub page needs {threshold}+)'
                fix = f'Add {threshold - n} more internal links to related pages'
                severity = SEVERITY_WARNING
        else:
            # Leaf: want parent + 3 related = 4 min
            threshold = 4
            if n >= threshold:
                score = max_score
                passed = True
                detail = f'{n} internal links (leaf page; threshold: {threshold})'
                fix = ''
                severity = SEVERITY_INFO
            elif n == 0:
                score = 0
                passed = False
                detail = 'No internal links — orphan page'
                fix = 'Add link to parent hub page + at least 3 related pages'
                severity = SEVERITY_CRITICAL
            else:
                score = round(max_score * (n / threshold), 1)
                passed = False
                detail = f'{n} internal links (leaf page needs {threshold}+)'
                fix = f'Add {threshold - n} more internal links (parent + related pages)'
                severity = SEVERITY_WARNING

        return CriterionResult(
            name='Cross-linking Density',
            score=min(score, max_score),
            max_score=max_score,
            passed=passed,
            severity=severity,
            detail=detail,
            fix=fix,
        )

    def _score_url_structure(self, file_path: str) -> CriterionResult:
        max_score = 10
        mapping = self._get_link_mapping()
        targets = self._get_inventory_targets()

        # Derive lookup key from file path
        rel = file_path
        for prefix in [
            str(_SCRIPTS_DIR.parent / 'df-docs' / 'df-docs' / 'docs') + '/',
            str(_SCRIPTS_DIR.parent / 'guide' / 'dreamfactory-book-v2' / 'content' / 'en' / 'docs') + '/',
            str(_SCRIPTS_DIR.parent) + '/',
        ]:
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
                break

        rel_no_ext = re.sub(r'\.(md|wiki)$', '', rel)
        key = rel_no_ext.lower()

        # Check if we can resolve to a wiki target
        target = mapping.get(key)
        if not target:
            slug = Path(rel_no_ext).stem.lower()
            target = mapping.get(slug)

        if target and target in targets:
            # Check semantic quality: should contain / separators
            has_hierarchy = '/' in target
            if has_hierarchy:
                return CriterionResult(
                    name='URL Structure',
                    score=max_score,
                    max_score=max_score,
                    passed=True,
                    severity=SEVERITY_INFO,
                    detail=f'Semantic wiki path: {target}',
                )
            else:
                return CriterionResult(
                    name='URL Structure',
                    score=round(max_score * 0.7, 1),
                    max_score=max_score,
                    passed=True,
                    severity=SEVERITY_INFO,
                    detail=f'Wiki path exists but flat: {target}',
                    fix='Consider a hierarchical path (e.g., Category/Page)',
                )
        elif target:
            return CriterionResult(
                name='URL Structure',
                score=round(max_score * 0.5, 1),
                max_score=max_score,
                passed=False,
                severity=SEVERITY_WARNING,
                detail=f'Mapped target "{target}" not in inventory targets',
                fix='Verify target_wiki_page in migration_inventory.csv',
            )
        else:
            return CriterionResult(
                name='URL Structure',
                score=0,
                max_score=max_score,
                passed=False,
                severity=SEVERITY_WARNING,
                detail='No inventory mapping found for this file',
                fix='Add entry to migration_inventory.csv with a semantic target_wiki_page',
            )

    def _score_structured_data(self, content: str) -> CriterionResult:
        max_score = 10
        # Look for JSON-LD or schema.org markup
        has_jsonld = bool(re.search(
            r'<script\s+type=["\']application/ld\+json["\']', content, re.IGNORECASE
        ))
        has_schema = bool(re.search(r'schema\.org', content, re.IGNORECASE))
        has_itemtype = bool(re.search(r'itemtype=["\']https?://schema\.org', content, re.IGNORECASE))

        if has_jsonld:
            return CriterionResult(
                name='Structured Data',
                score=max_score,
                max_score=max_score,
                passed=True,
                severity=SEVERITY_INFO,
                detail='JSON-LD block found',
            )
        elif has_schema or has_itemtype:
            return CriterionResult(
                name='Structured Data',
                score=round(max_score * 0.5, 1),
                max_score=max_score,
                passed=False,
                severity=SEVERITY_INFO,
                detail='Schema.org reference found but no JSON-LD block',
                fix='Add a <script type="application/ld+json"> block with TechArticle schema',
            )
        else:
            return CriterionResult(
                name='Structured Data',
                score=0,
                max_score=max_score,
                passed=False,
                severity=SEVERITY_INFO,
                detail='No structured data found (expected pre-upload; will be added via MediaWiki templates post-upload)',
                fix='Structured data (JSON-LD: TechArticle, BreadcrumbList, HowTo) will be injected via MediaWiki templates after upload — no action needed in source files',
            )

    def _score_code_examples(self, content: str, fmt: str) -> CriterionResult:
        max_score = 10
        count = 0

        if fmt == 'wiki':
            count += len(re.findall(r'<syntaxhighlight', content))
            count += len(re.findall(r'<source\b', content))
            count += len(re.findall(r'<code>', content))
            count += len(re.findall(r'<pre>', content))
        else:
            # Fenced code blocks
            count += len(re.findall(r'```', content)) // 2
            # Indented code blocks (4+ spaces at line start after blank line)
            # Only count these if no fenced blocks found
            if count == 0:
                lines = content.splitlines()
                in_code = False
                for i, line in enumerate(lines):
                    if line.startswith('    ') and i > 0 and not lines[i - 1].strip():
                        if not in_code:
                            count += 1
                            in_code = True
                    else:
                        in_code = False

        if count >= 1:
            return CriterionResult(
                name='Code Examples',
                score=max_score,
                max_score=max_score,
                passed=True,
                severity=SEVERITY_INFO,
                detail=f'{count} code block(s) found',
            )
        else:
            return CriterionResult(
                name='Code Examples',
                score=0,
                max_score=max_score,
                passed=False,
                severity=SEVERITY_WARNING,
                detail='No code examples found',
                fix='Add at least one code example (API call, config snippet, etc.)',
            )

    def _score_categories(
        self, content: str, fmt: str, frontmatter: Dict
    ) -> CriterionResult:
        max_score = 15

        if fmt == 'wiki':
            categories = re.findall(r'\[\[Category:([^\]]+)\]\]', content)
            if categories:
                return CriterionResult(
                    name='Categories',
                    score=max_score,
                    max_score=max_score,
                    passed=True,
                    severity=SEVERITY_INFO,
                    detail=f'{len(categories)} category tag(s): {", ".join(categories[:5])}',
                )
            else:
                return CriterionResult(
                    name='Categories',
                    score=0,
                    max_score=max_score,
                    passed=False,
                    severity=SEVERITY_WARNING,
                    detail='No [[Category:]] tags found',
                    fix='Add at least one [[Category:TopicName]] tag',
                )
        else:
            # Markdown: check frontmatter keywords
            keywords = frontmatter.get('keywords', [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(',') if k.strip()]
            if keywords:
                n = len(keywords)
                if n >= 3:
                    score = max_score
                else:
                    score = round(max_score * (n / 3), 1)
                return CriterionResult(
                    name='Categories',
                    score=min(score, max_score),
                    max_score=max_score,
                    passed=n >= 1,
                    severity=SEVERITY_INFO if n >= 3 else SEVERITY_WARNING,
                    detail=f'{n} frontmatter keyword(s)',
                    fix='' if n >= 3 else f'Add {3 - n} more keywords for better categorization',
                )
            else:
                return CriterionResult(
                    name='Categories',
                    score=0,
                    max_score=max_score,
                    passed=False,
                    severity=SEVERITY_WARNING,
                    detail='No frontmatter keywords found',
                    fix='Add keywords: [keyword1, keyword2, ...] to YAML frontmatter',
                )

    # -- link extraction ----------------------------------------------------

    @staticmethod
    def _extract_internal_links_wiki(content: str) -> List[str]:
        """Extract internal wiki links, excluding Category: and File: prefixes."""
        links = []
        for match in re.findall(r'\[\[([^\]|]+)', content):
            if not match.startswith(('Category:', 'File:', '#', 'http')):
                links.append(match.strip())
        return links

    @staticmethod
    def _extract_internal_links_md(body: str) -> List[str]:
        """Extract internal links from markdown body (exclude external URLs)."""
        links = []
        for match in re.findall(r'\[([^\]]*)\]\(([^)]+)\)', body):
            url = match[1]
            # Skip external URLs and anchors-only
            if url.startswith(('http://', 'https://', '#', 'mailto:')):
                continue
            # Skip images
            if url.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')):
                continue
            links.append(url)
        return links

    # -- hub detection ------------------------------------------------------

    def _is_hub_page(self, path: str, internal_links: List[str]) -> bool:
        """A page is a hub if it has >15 links or its path is a prefix of others."""
        if len(internal_links) > 15:
            return True

        # Check if this page's wiki target is a prefix of other pages
        mapping = self._get_link_mapping()
        rel = path
        for prefix in [
            str(_SCRIPTS_DIR.parent / 'df-docs' / 'df-docs' / 'docs') + '/',
            str(_SCRIPTS_DIR.parent / 'guide' / 'dreamfactory-book-v2' / 'content' / 'en' / 'docs') + '/',
            str(_SCRIPTS_DIR.parent) + '/',
        ]:
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
                break

        rel_no_ext = re.sub(r'\.(md|wiki)$', '', rel)
        key = rel_no_ext.lower()
        target = mapping.get(key)
        if not target:
            slug = Path(rel_no_ext).stem.lower()
            target = mapping.get(slug)

        if target:
            targets = self._get_inventory_targets()
            children = sum(
                1 for t in targets
                if t.startswith(target + '/') and t != target
            )
            if children >= 3:
                return True

        # Index/intro files are hubs
        stem = Path(path).stem.lower()
        if stem in ('index', '_index', 'introduction'):
            return True

        return False


# ---------------------------------------------------------------------------
# BatchScorer
# ---------------------------------------------------------------------------

class BatchScorer:
    """Score all files in a directory."""

    def __init__(self, inventory_path: Optional[str] = None, skip_drafts: bool = False):
        self.scorer = ContentScorer(inventory_path)
        self._skip_drafts = skip_drafts
        self._skip_sources: Optional[set] = None

    def _get_skip_sources(self) -> set:
        """Return set of relative paths (without prefix/ext) with status Skip-EmptyDraft."""
        if self._skip_sources is None:
            self._skip_sources = set()
            rows = self.scorer._get_inventory_rows()
            for row in rows:
                if row.get('status', '') == 'Skip-EmptyDraft':
                    src = row.get('source_path', '')
                    if src:
                        # Store the full source_path for exact matching
                        self._skip_sources.add(src.lower())
                        # Also store relative path without prefix
                        rel = src
                        for prefix in [
                            'df-docs/df-docs/docs/',
                            'guide/dreamfactory-book-v2/content/en/docs/',
                        ]:
                            if rel.startswith(prefix):
                                rel = rel[len(prefix):]
                                break
                        self._skip_sources.add(re.sub(r'\.md$', '', rel).lower())
        return self._skip_sources

    def _is_skipped_draft(self, fpath: Path) -> bool:
        """Check if a file corresponds to a Skip-EmptyDraft entry."""
        if not self._skip_drafts:
            return False
        skip_sources = self._get_skip_sources()
        fpath_str = str(fpath).lower()
        # Check if the file path ends with any of the skip source relative paths
        for skip_src in skip_sources:
            # Match against the end of the path to handle different root prefixes
            if fpath_str.endswith('/' + skip_src) or fpath_str.endswith('/' + skip_src + '.md'):
                return True
        return False

    def score_directory(self, dir_path: str, extensions: Tuple[str, ...] = ('.md', '.wiki')) -> List[ContentScore]:
        results = []
        root = Path(dir_path).resolve()
        skipped_drafts = 0
        for ext in extensions:
            for fpath in sorted(root.rglob(f'*{ext}')):
                # Skip hidden files and _ai-reference
                if any(part.startswith('.') and part not in ('.', '..') for part in fpath.parts):
                    continue
                if fpath.name == '_ai-reference.md':
                    continue
                if self._is_skipped_draft(fpath):
                    skipped_drafts += 1
                    continue
                try:
                    result = self.scorer.score_file(str(fpath))
                    results.append(result)
                except Exception as e:
                    print(f'ERROR scoring {fpath}: {e}', file=sys.stderr)
        if skipped_drafts:
            print(f'Skipped {skipped_drafts} draft file(s) (Skip-EmptyDraft)', file=sys.stderr)
        return results

    @staticmethod
    def write_csv(results: List[ContentScore], output_path: str) -> None:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            header = [
                'file_path', 'format', 'overall_score', 'word_count',
                'is_stub', 'is_hub',
                'word_count_score', 'version_currency_score',
                'crosslinks_score', 'url_structure_score',
                'structured_data_score', 'code_examples_score',
                'categories_score',
            ]
            writer.writerow(header)
            for r in results:
                scores = {c.name: c.score for c in r.criteria}
                writer.writerow([
                    r.file_path,
                    r.format,
                    r.overall_score,
                    r.word_count,
                    r.is_stub,
                    r.is_hub,
                    scores.get('Word Count', 0),
                    scores.get('Version Currency', 0),
                    scores.get('Cross-linking Density', 0),
                    scores.get('URL Structure', 0),
                    scores.get('Structured Data', 0),
                    scores.get('Code Examples', 0),
                    scores.get('Categories', 0),
                ])

    @staticmethod
    def print_summary(results: List[ContentScore], threshold: int = 0) -> None:
        if not results:
            print('No files scored.', file=sys.stderr)
            return

        scores = [r.overall_score for r in results]
        avg = sum(scores) / len(scores)
        stubs = sum(1 for r in results if r.is_stub)
        hubs = sum(1 for r in results if r.is_hub)

        print('\n' + '=' * 60, file=sys.stderr)
        print('CONTENT SCORE SUMMARY', file=sys.stderr)
        print('=' * 60, file=sys.stderr)
        print(f'Files scored:    {len(results)}', file=sys.stderr)
        print(f'Average score:   {avg:.1f}/100', file=sys.stderr)
        print(f'Highest:         {max(scores):.1f}', file=sys.stderr)
        print(f'Lowest:          {min(scores):.1f}', file=sys.stderr)
        print(f'Stubs (<100w):   {stubs}', file=sys.stderr)
        print(f'Hub pages:       {hubs}', file=sys.stderr)

        if threshold > 0:
            passing = sum(1 for s in scores if s >= threshold)
            failing = len(scores) - passing
            print(f'Threshold:       {threshold}', file=sys.stderr)
            print(f'Passing:         {passing} ({passing / len(scores) * 100:.0f}%)', file=sys.stderr)
            print(f'Failing:         {failing} ({failing / len(scores) * 100:.0f}%)', file=sys.stderr)

        # Bottom 10
        sorted_results = sorted(results, key=lambda r: r.overall_score)
        bottom = sorted_results[:10]
        print(f'\nBottom {len(bottom)} files:', file=sys.stderr)
        for r in bottom:
            stub = ' [STUB]' if r.is_stub else ''
            hub = ' [HUB]' if r.is_hub else ''
            print(f'  {r.overall_score:5.1f}  {r.file_path}{stub}{hub}', file=sys.stderr)

        # Per-criterion averages
        criterion_totals: Dict[str, List[float]] = {}
        criterion_maxes: Dict[str, float] = {}
        for r in results:
            for c in r.criteria:
                criterion_totals.setdefault(c.name, []).append(c.score)
                criterion_maxes[c.name] = c.max_score

        print('\nPer-criterion averages:', file=sys.stderr)
        for name in criterion_totals:
            vals = criterion_totals[name]
            mx = criterion_maxes[name]
            avg_c = sum(vals) / len(vals)
            print(f'  {name:25s}  {avg_c:5.1f}/{mx:.0f}  ({avg_c / mx * 100:.0f}%)', file=sys.stderr)

        print('=' * 60, file=sys.stderr)


# ---------------------------------------------------------------------------
# Text formatter for single-file output
# ---------------------------------------------------------------------------

def format_text_report(result: ContentScore) -> str:
    """Human-readable text report for a single file."""
    lines = []
    lines.append(f'Content Score: {result.file_path}')
    lines.append(f'Format: {result.format}  |  Words: {result.word_count}'
                 f'  |  Hub: {"Yes" if result.is_hub else "No"}'
                 f'  |  Stub: {"Yes" if result.is_stub else "No"}')
    lines.append('')
    lines.append(f'{"#":<3} {"Criterion":<25} {"Score":>6} {"Max":>5} {"Status":<8} Detail')
    lines.append('-' * 90)

    for i, c in enumerate(result.criteria, 1):
        status = 'PASS' if c.passed else 'FAIL'
        lines.append(f'{i:<3} {c.name:<25} {c.score:>6.1f} {c.max_score:>5.0f} {status:<8} {c.detail}')

    lines.append('-' * 90)
    lines.append(f'{"":3} {"OVERALL":<25} {result.overall_score:>6.1f} {"100":>5}')
    lines.append('')

    # Fix recommendations
    fixes = [
        (c.max_score - c.score, c) for c in result.criteria if c.fix
    ]
    fixes.sort(key=lambda x: x[0], reverse=True)

    if fixes:
        lines.append('Fix Recommendations (by priority):')
        for i, (gap, c) in enumerate(fixes, 1):
            lines.append(f'  {i}. [{c.severity}] {c.name} ({c.score:.0f}/{c.max_score:.0f}): {c.detail}')
            if c.fix:
                lines.append(f'     → {c.fix}')
    else:
        lines.append('No fixes needed — all criteria passed.')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Score documentation files against SEO/content quality criteria.'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--file', '-f', help='Score a single file')
    group.add_argument('--dir', '-d', help='Score all files in a directory')
    parser.add_argument('--output', '-o', help='CSV output path (batch mode)')
    parser.add_argument(
        '--format', choices=['text', 'json'], default='text',
        help='Output format (default: text)',
    )
    parser.add_argument(
        '--threshold', '-t', type=int, default=0,
        help='Minimum passing score for CI gating (exit code 1 if any file below)',
    )
    parser.add_argument(
        '--inventory', help='Path to migration_inventory.csv (default: auto-detect)',
    )
    parser.add_argument(
        '--skip-drafts', action='store_true',
        help='Exclude files marked Skip-EmptyDraft in migration_inventory.csv',
    )

    args = parser.parse_args()

    if args.file:
        # -- Single file mode --
        fpath = Path(args.file)
        if not fpath.exists():
            print(f'Error: file not found: {args.file}', file=sys.stderr)
            sys.exit(2)

        scorer = ContentScorer(args.inventory)
        result = scorer.score_file(str(fpath))

        if args.format == 'json':
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(format_text_report(result))

        if args.threshold and result.overall_score < args.threshold:
            sys.exit(1)

    elif args.dir:
        # -- Batch mode --
        dpath = Path(args.dir)
        if not dpath.is_dir():
            print(f'Error: directory not found: {args.dir}', file=sys.stderr)
            sys.exit(2)

        batch = BatchScorer(args.inventory, skip_drafts=args.skip_drafts)
        results = batch.score_directory(str(dpath))

        if not results:
            print('No .md or .wiki files found.', file=sys.stderr)
            sys.exit(2)

        if args.output:
            batch.write_csv(results, args.output)
            print(f'CSV report written to {args.output}', file=sys.stderr)

        if args.format == 'json':
            print(json.dumps([r.to_dict() for r in results], indent=2))

        batch.print_summary(results, args.threshold)

        if args.threshold:
            failing = [r for r in results if r.overall_score < args.threshold]
            if failing:
                sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
