#!/usr/bin/env python3
"""
test_wiki_site.py - Integration tests for the live staging wiki

Crawls the rendered wiki via the MediaWiki API and reports:
  1. Sidebar navigation red links
  2. Internal red links across all pages
  3. Page rendering errors (parse warnings, broken tables, strip markers)
  4. Missing images (wanted files)
  5. Broken external links (HEAD check with thread pool)
  6. Empty categories
  7. Table of contents heading-level skips
  8. Code block rendering issues
  9. Missing or broken templates

Usage:
    .venv/bin/python test_wiki_site.py --wiki-url http://localhost:8082
    .venv/bin/python test_wiki_site.py --wiki-url http://localhost:8082 \
        --output-json report.json --skip-external --verbose
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    check: str
    severity: str  # ERROR, WARNING
    page: str
    detail: str
    url: str = ''


@dataclass
class CheckResult:
    name: str
    total: int
    passed: int
    warnings: int
    errors: int
    issues: List[Issue] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def status(self) -> str:
        if self.errors > 0:
            return 'FAIL'
        if self.warnings > 0:
            return 'WARN'
        return 'PASS'


@dataclass
class TestReport:
    wiki_url: str
    timestamp: str
    total_pages: int
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        return all(c.errors == 0 for c in self.checks)

    def to_dict(self) -> dict:
        d = {
            'wiki_url': self.wiki_url,
            'timestamp': self.timestamp,
            'total_pages': self.total_pages,
            'overall_pass': self.overall_pass,
            'checks': [],
        }
        for c in self.checks:
            cd = asdict(c)
            cd['status'] = c.status
            d['checks'].append(cd)
        return d


# ---------------------------------------------------------------------------
# WikiAPI — thin requests wrapper with auto-continuation
# ---------------------------------------------------------------------------

class WikiAPI:
    """MediaWiki API client with automatic continuation support."""

    def __init__(self, wiki_url: str, timeout: int = 10):
        self.api_url = wiki_url.rstrip('/') + '/api.php'
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'WikiSiteTest/1.0 (integration-test)'

    def query(self, **params) -> dict:
        """Single API call, returns parsed JSON."""
        params.setdefault('format', 'json')
        resp = self.session.get(self.api_url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def query_continue(self, **params) -> list:
        """Auto-continuing query. Yields merged result batches."""
        params.setdefault('format', 'json')
        results = []
        while True:
            data = self.query(**params)
            results.append(data)
            if 'continue' not in data:
                break
            params.update(data['continue'])
        return results

    def get_all_pages(self, namespace: int = 0) -> List[str]:
        """Return all page titles in a namespace."""
        titles = []
        params = {
            'action': 'query',
            'list': 'allpages',
            'aplimit': '500',
            'apnamespace': str(namespace),
        }
        for batch in self.query_continue(**params):
            for page in batch.get('query', {}).get('allpages', []):
                titles.append(page['title'])
        return titles

    def parse_page(self, title: str, timeout: Optional[int] = None) -> dict:
        """Parse a page, returning text, parsewarnings, sections, and wikitext."""
        params = {
            'action': 'parse',
            'page': title,
            'prop': 'text|parsewarnings|sections|wikitext',
            'format': 'json',
        }
        t = timeout or self.timeout
        resp = self.session.get(self.api_url, params=params, timeout=t)
        resp.raise_for_status()
        return resp.json().get('parse', {})

    # MediaWiki magic words used in sidebar that are not real page titles
    _SIDEBAR_MAGIC_WORDS = {
        'mainpage', 'mainpage-description', 'SEARCH', 'TOOLBOX',
        'LANGUAGES', 'navigation', 'recentchanges-url',
    }

    def get_sidebar_links(self) -> List[str]:
        """Fetch MediaWiki:Sidebar wikitext and extract page names."""
        data = self.query(
            action='parse',
            page='MediaWiki:Sidebar',
            prop='wikitext',
        )
        wikitext = data.get('parse', {}).get('wikitext', {}).get('*', '')
        pages = []
        for line in wikitext.splitlines():
            line = line.strip()
            if not line or line.startswith('*') is False:
                if '|' in line:
                    parts = line.split('|', 1)
                    page = parts[0].strip().lstrip('*').strip()
                    if (page and page not in self._SIDEBAR_MAGIC_WORDS
                            and not page.startswith('#')
                            and not page.startswith('Special:')):
                        pages.append(page)
                continue
            # Lines like "** Page_Name|Display Text" or "* navigation"
            if '|' in line:
                parts = line.lstrip('*').strip().split('|', 1)
                page = parts[0].strip()
                if (page and page not in self._SIDEBAR_MAGIC_WORDS
                        and not page.startswith('#')
                        and not page.startswith('Special:')):
                    pages.append(page)
        return pages

    def check_pages_exist(self, titles: List[str]) -> Dict[str, bool]:
        """Batch-check whether pages exist. Returns {title: exists}."""
        result = {}
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            data = self.query(
                action='query',
                titles='|'.join(batch),
            )
            for page in data.get('query', {}).get('pages', {}).values():
                title = page.get('title', '')
                exists = 'missing' not in page
                result[title] = exists
            # Handle normalized titles
            for norm in data.get('query', {}).get('normalized', []):
                if norm['to'] in result:
                    result[norm['from']] = result[norm['to']]
        return result

    def get_all_links(self) -> List[Tuple[str, str]]:
        """Get all internal links: (source_page, target_page) pairs."""
        links = []
        params = {
            'action': 'query',
            'generator': 'allpages',
            'gaplimit': '50',
            'gapnamespace': '0',
            'prop': 'links',
            'pllimit': '500',
        }
        for batch in self.query_continue(**params):
            pages = batch.get('query', {}).get('pages', {})
            for page in pages.values():
                source = page.get('title', '')
                for link in page.get('links', []):
                    target = link.get('title', '')
                    if 'missing' in link:
                        links.append((source, target))
        return links

    def get_wanted_files(self) -> List[dict]:
        """Get files referenced but not uploaded."""
        results = []
        params = {
            'action': 'query',
            'list': 'querypage',
            'qppage': 'Wantedfiles',
            'qplimit': '500',
        }
        for batch in self.query_continue(**params):
            for item in batch.get('query', {}).get('querypage', {}).get('results', []):
                results.append(item)
        return results

    def get_wanted_templates(self) -> List[dict]:
        """Get templates referenced but not created."""
        results = []
        params = {
            'action': 'query',
            'list': 'querypage',
            'qppage': 'Wantedtemplates',
            'qplimit': '500',
        }
        for batch in self.query_continue(**params):
            for item in batch.get('query', {}).get('querypage', {}).get('results', []):
                results.append(item)
        return results

    def get_all_categories(self) -> List[dict]:
        """Get all categories with member counts."""
        cats = []
        params = {
            'action': 'query',
            'list': 'allcategories',
            'aclimit': '500',
            'acprop': 'size',
        }
        for batch in self.query_continue(**params):
            for cat in batch.get('query', {}).get('allcategories', []):
                cats.append(cat)
        return cats

    def get_external_links(self) -> List[Tuple[str, str]]:
        """Get all external URLs: (page_title, url) pairs."""
        links = []
        params = {
            'action': 'query',
            'list': 'exturlusage',
            'eulimit': '500',
        }
        for batch in self.query_continue(**params):
            for item in batch.get('query', {}).get('exturlusage', []):
                links.append((item.get('title', ''), item.get('url', '')))
        return links


# ---------------------------------------------------------------------------
# Checkers
# ---------------------------------------------------------------------------

class NavigationChecker:
    """Check 1: Sidebar navigation — verify all sidebar links exist."""

    def __init__(self, api: WikiAPI):
        self.api = api

    def run(self) -> CheckResult:
        t0 = time.monotonic()
        issues = []

        sidebar_pages = self.api.get_sidebar_links()
        if not sidebar_pages:
            return CheckResult(
                name='Sidebar Navigation',
                total=0, passed=0, warnings=0, errors=0,
                issues=[Issue('navigation', 'WARNING', '', 'No sidebar links found')],
                elapsed=time.monotonic() - t0,
            )

        existence = self.api.check_pages_exist(sidebar_pages)
        errors = 0
        for page in sidebar_pages:
            if not existence.get(page, True):
                issues.append(Issue(
                    'navigation', 'ERROR', page,
                    f'Sidebar links to non-existent page: {page}',
                ))
                errors += 1

        return CheckResult(
            name='Sidebar Navigation',
            total=len(sidebar_pages),
            passed=len(sidebar_pages) - errors,
            warnings=0,
            errors=errors,
            issues=issues,
            elapsed=time.monotonic() - t0,
        )


class InternalLinkChecker:
    """Check 2: Internal red links across all pages."""

    def __init__(self, api: WikiAPI):
        self.api = api

    def run(self) -> CheckResult:
        t0 = time.monotonic()
        issues = []

        red_links = self.api.get_all_links()
        # Deduplicate
        seen = set()
        unique_red = []
        for source, target in red_links:
            key = (source, target)
            if key not in seen:
                seen.add(key)
                unique_red.append((source, target))

        # Get total link count for reporting
        all_pages = self.api.get_all_pages()
        total_links = len(all_pages)  # approximate: 1 check per page

        for source, target in unique_red:
            issues.append(Issue(
                'internal_links', 'ERROR', source,
                f'Red link: "{source}" -> "{target}"',
            ))

        return CheckResult(
            name='Internal Links',
            total=total_links,
            passed=total_links - len(unique_red),
            warnings=0,
            errors=len(unique_red),
            issues=issues,
            elapsed=time.monotonic() - t0,
        )


class RenderingChecker:
    """Check 3: Page rendering — parse warnings, error spans, broken tables, strip markers."""

    def __init__(self, api: WikiAPI, verbose: bool = False):
        self.api = api
        self.verbose = verbose
        self.parse_cache: Dict[str, dict] = {}

    def run(self, pages: Optional[List[str]] = None) -> CheckResult:
        t0 = time.monotonic()
        issues = []

        if pages is None:
            pages = self.api.get_all_pages()

        errors = 0
        warnings = 0
        # Use a longer timeout for parsing since some pages are heavy
        parse_timeout = max(self.api.timeout, 30)

        for title in pages:
            try:
                parsed = self.api.parse_page(title, timeout=parse_timeout)
                self.parse_cache[title] = parsed
            except requests.RequestException as e:
                issues.append(Issue('rendering', 'ERROR', title, f'Parse failed for "{title}": {e}'))
                errors += 1
                continue

            html = parsed.get('text', {}).get('*', '')
            wikitext = parsed.get('wikitext', {}).get('*', '')
            parse_warnings = parsed.get('parsewarnings', [])

            # Parse warnings
            for pw in parse_warnings:
                issues.append(Issue('rendering', 'WARNING', title, f'Parse warning: {pw}'))
                warnings += 1

            # Error spans
            if 'class="error"' in html:
                error_count = html.count('class="error"')
                issues.append(Issue(
                    'rendering', 'ERROR', title,
                    f'{error_count} error span(s) in rendered HTML',
                ))
                errors += 1

            # Broken tables — literal {| or |} outside <pre>/<code>
            # Strip content inside <pre> and <code> before checking
            html_stripped = re.sub(r'<pre[^>]*>.*?</pre>', '', html, flags=re.DOTALL)
            html_stripped = re.sub(r'<code[^>]*>.*?</code>', '', html_stripped, flags=re.DOTALL)
            if '{|' in html_stripped or '|}' in html_stripped:
                issues.append(Issue(
                    'rendering', 'ERROR', title,
                    'Broken wiki table markup visible in rendered HTML',
                ))
                errors += 1

            # Strip-marker leaks
            if 'UNIQ--' in html:
                issues.append(Issue(
                    'rendering', 'ERROR', title,
                    'Strip-marker leak (UNIQ--) in rendered HTML',
                ))
                errors += 1

        return CheckResult(
            name='Page Rendering',
            total=len(pages),
            passed=len(pages) - errors,
            warnings=warnings,
            errors=errors,
            issues=issues,
            elapsed=time.monotonic() - t0,
        )


class ImageChecker:
    """Check 4: Missing images (wanted files)."""

    def __init__(self, api: WikiAPI):
        self.api = api

    def run(self) -> CheckResult:
        t0 = time.monotonic()
        issues = []

        wanted = self.api.get_wanted_files()
        for item in wanted:
            title = item.get('title', '')
            value = item.get('value', 0)
            issues.append(Issue(
                'images', 'WARNING', title,
                f'{title} — missing file referenced by {value} page(s)',
            ))

        # Get total image count from allimages
        all_images_data = self.api.query(
            action='query', list='allimages', ailimit='1',
            aiprop='',
        )
        # Also count the wanted ones for total
        # Use a simple allimages count
        total_images = 0
        params = {'action': 'query', 'list': 'allimages', 'ailimit': '500', 'aiprop': ''}
        for batch in self.api.query_continue(**params):
            total_images += len(batch.get('query', {}).get('allimages', []))

        total = total_images + len(wanted)

        return CheckResult(
            name='Images',
            total=total,
            passed=total_images,
            warnings=len(wanted),
            errors=0,
            issues=issues,
            elapsed=time.monotonic() - t0,
        )


class ExternalLinkChecker:
    """Check 5: External links — HEAD check with thread pool."""

    def __init__(self, api: WikiAPI, timeout: int = 5, max_workers: int = 10):
        self.api = api
        self.timeout = timeout
        self.max_workers = max_workers

    def _check_url(self, url: str) -> Tuple[str, Optional[int], Optional[str]]:
        """HEAD-check a URL. Returns (url, status_code, error_msg)."""
        try:
            resp = requests.head(url, timeout=self.timeout, allow_redirects=True,
                                 headers={'User-Agent': 'WikiSiteTest/1.0'})
            return (url, resp.status_code, None)
        except requests.Timeout:
            return (url, None, 'timeout')
        except requests.ConnectionError:
            return (url, None, 'connection error')
        except requests.RequestException as e:
            return (url, None, str(e))

    def run(self) -> CheckResult:
        t0 = time.monotonic()
        issues = []

        ext_links = self.api.get_external_links()
        # Deduplicate URLs, keeping track of source pages
        url_pages: Dict[str, List[str]] = {}
        for page, url in ext_links:
            if not url:
                continue
            # Skip localhost/local URLs
            if any(h in url for h in ['localhost', '127.0.0.1', '0.0.0.0']):
                continue
            url_pages.setdefault(url, []).append(page)

        unique_urls = list(url_pages.keys())
        errors = 0
        warnings = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self._check_url, url): url for url in unique_urls}
            for future in as_completed(futures):
                url, status, error = future.result()
                pages = url_pages.get(url, ['?'])
                source = pages[0]

                if status is not None:
                    if status in (404, 410):
                        issues.append(Issue(
                            'external_links', 'ERROR', source,
                            f'{url} -> {status}',
                            url=url,
                        ))
                        errors += 1
                    elif status >= 500:
                        issues.append(Issue(
                            'external_links', 'WARNING', source,
                            f'{url} -> {status}',
                            url=url,
                        ))
                        warnings += 1
                else:
                    issues.append(Issue(
                        'external_links', 'WARNING', source,
                        f'{url} -> {error}',
                        url=url,
                    ))
                    warnings += 1

        return CheckResult(
            name='External Links',
            total=len(unique_urls),
            passed=len(unique_urls) - errors - warnings,
            warnings=warnings,
            errors=errors,
            issues=issues,
            elapsed=time.monotonic() - t0,
        )


class CategoryChecker:
    """Check 6: Empty categories."""

    def __init__(self, api: WikiAPI):
        self.api = api

    def run(self) -> CheckResult:
        t0 = time.monotonic()
        issues = []

        categories = self.api.get_all_categories()
        warnings = 0

        for cat in categories:
            name = cat.get('*', cat.get('category', ''))
            size = cat.get('size', 0)
            if size == 0:
                issues.append(Issue(
                    'categories', 'WARNING', f'Category:{name}',
                    f'Empty category with 0 members',
                ))
                warnings += 1

        return CheckResult(
            name='Categories',
            total=len(categories),
            passed=len(categories) - warnings,
            warnings=warnings,
            errors=0,
            issues=issues,
            elapsed=time.monotonic() - t0,
        )


class TOCChecker:
    """Check 7: Table of contents — heading level skips."""

    def __init__(self, parse_cache: Dict[str, dict]):
        self.parse_cache = parse_cache

    def run(self) -> CheckResult:
        t0 = time.monotonic()
        issues = []
        checked = 0
        errors = 0

        for title, parsed in self.parse_cache.items():
            sections = parsed.get('sections', [])
            if len(sections) < 4:
                continue

            checked += 1
            levels = [int(s.get('level', 0)) for s in sections if s.get('level')]
            if not levels:
                continue

            # Check for heading-level skips
            for i in range(1, len(levels)):
                if levels[i] > levels[i - 1] + 1:
                    issues.append(Issue(
                        'toc', 'WARNING', title,
                        f'Heading skip: h{levels[i-1]} -> h{levels[i]} '
                        f'(section "{sections[i].get("line", "?")}")',
                    ))
                    errors += 1
                    break  # One report per page

        return CheckResult(
            name='Table of Contents',
            total=checked,
            passed=checked - errors,
            warnings=errors,  # heading skips are warnings, not fatal
            errors=0,
            issues=issues,
            elapsed=time.monotonic() - t0,
        )


class CodeBlockChecker:
    """Check 8: Code block rendering — ensure syntaxhighlight renders correctly."""

    def __init__(self, parse_cache: Dict[str, dict]):
        self.parse_cache = parse_cache

    def run(self) -> CheckResult:
        t0 = time.monotonic()
        issues = []
        checked = 0
        errors = 0

        for title, parsed in self.parse_cache.items():
            wikitext = parsed.get('wikitext', {}).get('*', '')
            html = parsed.get('text', {}).get('*', '')

            sh_count = len(re.findall(r'<syntaxhighlight', wikitext))
            if sh_count == 0:
                continue

            checked += 1

            # Check rendered HTML contains highlighted code
            has_highlight = 'class="mw-highlight' in html or 'class="mw-code' in html
            # Check for literal <syntaxhighlight in rendered output (unrendered tag)
            # Strip <pre>/<code> content first
            html_stripped = re.sub(r'<pre[^>]*>.*?</pre>', '', html, flags=re.DOTALL)
            html_stripped = re.sub(r'<code[^>]*>.*?</code>', '', html_stripped, flags=re.DOTALL)
            has_literal = '<syntaxhighlight' in html_stripped

            if has_literal:
                issues.append(Issue(
                    'code_blocks', 'ERROR', title,
                    f'Literal <syntaxhighlight> tag visible in rendered HTML '
                    f'({sh_count} block(s) in wikitext)',
                ))
                errors += 1
            elif not has_highlight and sh_count > 0:
                issues.append(Issue(
                    'code_blocks', 'WARNING', title,
                    f'{sh_count} syntaxhighlight block(s) in wikitext but '
                    f'no mw-highlight class in rendered HTML',
                ))

        return CheckResult(
            name='Code Blocks',
            total=checked,
            passed=checked - errors,
            warnings=len([i for i in issues if i.severity == 'WARNING']),
            errors=errors,
            issues=issues,
            elapsed=time.monotonic() - t0,
        )


class TemplateChecker:
    """Check 9: Templates — wanted templates + expected templates + raw template text."""

    EXPECTED_TEMPLATES = [
        'Warning', 'Note', 'Tip', 'VersionBanner',
        'API Endpoint', 'InfoBox',
    ]

    def __init__(self, api: WikiAPI, parse_cache: Dict[str, dict]):
        self.api = api
        self.parse_cache = parse_cache

    def run(self) -> CheckResult:
        t0 = time.monotonic()
        issues = []
        errors = 0
        warnings = 0
        total = 0

        # Wanted templates
        wanted = self.api.get_wanted_templates()
        for item in wanted:
            title = item.get('title', '')
            value = item.get('value', 0)
            issues.append(Issue(
                'templates', 'ERROR', title,
                f'Missing template referenced by {value} page(s)',
            ))
            errors += 1
            total += 1

        # Check expected templates exist
        template_titles = [f'Template:{t}' for t in self.EXPECTED_TEMPLATES]
        existence = self.api.check_pages_exist(template_titles)
        for tmpl_title in template_titles:
            total += 1
            if not existence.get(tmpl_title, True):
                issues.append(Issue(
                    'templates', 'WARNING', tmpl_title,
                    f'Expected template does not exist: {tmpl_title}',
                ))
                warnings += 1

        # Sample check: raw {{TemplateName| visible in rendered output
        for title, parsed in self.parse_cache.items():
            html = parsed.get('text', {}).get('*', '')
            # Strip <pre>/<code> content
            html_stripped = re.sub(r'<pre[^>]*>.*?</pre>', '', html, flags=re.DOTALL)
            html_stripped = re.sub(r'<code[^>]*>.*?</code>', '', html_stripped, flags=re.DOTALL)
            # Look for raw template invocations
            raw_templates = re.findall(r'\{\{(\w+)\s*\|', html_stripped)
            if raw_templates:
                total += 1
                issues.append(Issue(
                    'templates', 'ERROR', title,
                    f'Raw template text visible: {{{{{raw_templates[0]}|...}}}}',
                ))
                errors += 1

        # Count total as wanted + expected + sampled
        passed = total - errors - warnings

        return CheckResult(
            name='Templates',
            total=max(total, 1),
            passed=max(passed, 0),
            warnings=warnings,
            errors=errors,
            issues=issues,
            elapsed=time.monotonic() - t0,
        )


# ---------------------------------------------------------------------------
# TestRunner — orchestrator
# ---------------------------------------------------------------------------

class TestRunner:
    """Runs all checks and produces the report."""

    CHECK_NAMES = {
        'navigation': 'Sidebar Navigation',
        'internal_links': 'Internal Links',
        'rendering': 'Page Rendering',
        'images': 'Images',
        'external_links': 'External Links',
        'categories': 'Categories',
        'toc': 'Table of Contents',
        'code_blocks': 'Code Blocks',
        'templates': 'Templates',
    }

    def __init__(self, wiki_url: str, timeout: int = 10,
                 skip_external: bool = False, checks: Optional[List[str]] = None,
                 verbose: bool = False):
        self.wiki_url = wiki_url
        self.api = WikiAPI(wiki_url, timeout=timeout)
        self.skip_external = skip_external
        self.enabled_checks = checks or list(self.CHECK_NAMES.keys())
        self.verbose = verbose

    def run(self) -> TestReport:
        report = TestReport(
            wiki_url=self.wiki_url,
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_pages=0,
        )

        # Get total page count
        try:
            all_pages = self.api.get_all_pages()
            report.total_pages = len(all_pages)
        except requests.RequestException as e:
            print(f"FATAL: Cannot connect to {self.wiki_url}: {e}", file=sys.stderr)
            sys.exit(2)

        print(f"Connected to {self.wiki_url} — {report.total_pages} pages\n",
              file=sys.stderr)

        # Check 1: Navigation
        if 'navigation' in self.enabled_checks:
            self._run_check(report, 1, 'navigation',
                            lambda: NavigationChecker(self.api).run())

        # Check 2: Internal links
        if 'internal_links' in self.enabled_checks:
            self._run_check(report, 2, 'internal_links',
                            lambda: InternalLinkChecker(self.api).run())

        # Check 3: Rendering (also populates parse cache for checks 7, 8, 9)
        rendering_checker = RenderingChecker(self.api, self.verbose)
        if 'rendering' in self.enabled_checks:
            self._run_check(report, 3, 'rendering',
                            lambda: rendering_checker.run(all_pages))
        else:
            # Still need parse cache for downstream checks
            needs_cache = {'toc', 'code_blocks', 'templates'} & set(self.enabled_checks)
            if needs_cache:
                print("  Populating parse cache...", file=sys.stderr)
                rendering_checker.run(all_pages)

        parse_cache = rendering_checker.parse_cache

        # Check 4: Images
        if 'images' in self.enabled_checks:
            self._run_check(report, 4, 'images',
                            lambda: ImageChecker(self.api).run())

        # Check 5: External links
        if 'external_links' in self.enabled_checks and not self.skip_external:
            self._run_check(report, 5, 'external_links',
                            lambda: ExternalLinkChecker(self.api).run())
        elif 'external_links' in self.enabled_checks and self.skip_external:
            print("  5. External Links ......................... SKIP (--skip-external)",
                  file=sys.stderr)

        # Check 6: Categories
        if 'categories' in self.enabled_checks:
            self._run_check(report, 6, 'categories',
                            lambda: CategoryChecker(self.api).run())

        # Check 7: TOC (reuses parse cache)
        if 'toc' in self.enabled_checks:
            self._run_check(report, 7, 'toc',
                            lambda: TOCChecker(parse_cache).run())

        # Check 8: Code blocks (reuses parse cache)
        if 'code_blocks' in self.enabled_checks:
            self._run_check(report, 8, 'code_blocks',
                            lambda: CodeBlockChecker(parse_cache).run())

        # Check 9: Templates
        if 'templates' in self.enabled_checks:
            self._run_check(report, 9, 'templates',
                            lambda: TemplateChecker(self.api, parse_cache).run())

        return report

    def _run_check(self, report: TestReport, num: int, key: str, fn):
        """Run a single check with error handling and progress output."""
        name = self.CHECK_NAMES[key]
        try:
            result = fn()
            report.checks.append(result)
            status_str = result.status
            count_str = f'({result.passed}/{result.total})'
            dots = '.' * max(1, 48 - len(name) - len(count_str))
            print(f"  {num}. {name} {dots} {status_str} {count_str}  [{result.elapsed:.1f}s]",
                  file=sys.stderr)
            if self.verbose or result.issues:
                shown = 0
                for issue in result.issues:
                    prefix = 'ERROR' if issue.severity == 'ERROR' else 'WARNING'
                    print(f"     {prefix}: {issue.detail}", file=sys.stderr)
                    shown += 1
                    if not self.verbose and shown >= 10:
                        remaining = len(result.issues) - shown
                        if remaining > 0:
                            print(f"     ... and {remaining} more", file=sys.stderr)
                        break
        except requests.RequestException as e:
            result = CheckResult(
                name=name, total=0, passed=0, warnings=0, errors=1,
                issues=[Issue(key, 'ERROR', '', f'Check failed: {e}')],
            )
            report.checks.append(result)
            print(f"  {num}. {name} {'.' * 30} FAIL (connection error)",
                  file=sys.stderr)

    def format_text(self, report: TestReport) -> str:
        """Format the report as human-readable text."""
        lines = []
        lines.append('=' * 64)
        lines.append(f'  WIKI SITE TEST REPORT — {report.wiki_url}')
        lines.append(f'  {report.timestamp}')
        lines.append(f'  Total pages: {report.total_pages}')
        lines.append('=' * 64)
        lines.append('')

        for i, check in enumerate(report.checks, 1):
            status = check.status
            count = f'({check.passed}/{check.total})'
            name = check.name
            dots = '.' * max(1, 48 - len(name) - len(count))
            lines.append(f'{i:2}. {name} {dots} {status} {count}')
            for issue in check.issues:
                prefix = issue.severity
                lines.append(f'    {prefix}: {issue.detail}')

        lines.append('')
        lines.append('=' * 64)

        passed = sum(1 for c in report.checks if c.status == 'PASS')
        warned = sum(1 for c in report.checks if c.status == 'WARN')
        failed = sum(1 for c in report.checks if c.status == 'FAIL')
        total_time = sum(c.elapsed for c in report.checks)

        parts = []
        if passed:
            parts.append(f'{passed} passed')
        if warned:
            parts.append(f'{warned} warnings')
        if failed:
            parts.append(f'{failed} failed')

        lines.append(f'  SUMMARY: {", ".join(parts)} | {total_time:.1f}s')
        lines.append('=' * 64)

        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Integration tests for the live staging wiki.'
    )
    parser.add_argument(
        '--wiki-url', default='http://localhost:8082',
        help='MediaWiki base URL (default: http://localhost:8082)',
    )
    parser.add_argument(
        '--output-json', metavar='PATH',
        help='Write machine-readable JSON report to file',
    )
    parser.add_argument(
        '--output-text', metavar='PATH',
        help='Write text report to file (default: stdout)',
    )
    parser.add_argument(
        '--skip-external', action='store_true',
        help='Skip external link checks',
    )
    parser.add_argument(
        '--checks', metavar='LIST',
        help='Comma-separated subset of checks to run '
             '(navigation,internal_links,rendering,images,'
             'external_links,categories,toc,code_blocks,templates)',
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show all items, not just failures',
    )
    parser.add_argument(
        '--timeout', type=int, default=10,
        help='HTTP timeout in seconds (default: 10)',
    )

    args = parser.parse_args()

    checks = None
    if args.checks:
        checks = [c.strip() for c in args.checks.split(',')]
        valid = set(TestRunner.CHECK_NAMES.keys())
        invalid = set(checks) - valid
        if invalid:
            print(f"Error: unknown check(s): {', '.join(invalid)}", file=sys.stderr)
            print(f"Valid checks: {', '.join(sorted(valid))}", file=sys.stderr)
            sys.exit(2)

    runner = TestRunner(
        wiki_url=args.wiki_url,
        timeout=args.timeout,
        skip_external=args.skip_external,
        checks=checks,
        verbose=args.verbose,
    )

    report = runner.run()

    # Output
    text = runner.format_text(report)

    if args.output_text:
        with open(args.output_text, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"\nText report written to {args.output_text}", file=sys.stderr)
    else:
        print()
        print(text)

    if args.output_json:
        with open(args.output_json, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"JSON report written to {args.output_json}", file=sys.stderr)

    # Exit code
    if report.overall_pass:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
