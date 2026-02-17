#!/usr/bin/env python3
"""
postprocess.py - Fix Pandoc conversion issues for MediaWiki

Post-processes Pandoc-converted MediaWiki files to fix:
- Extract YAML frontmatter for categories/metadata
- Fix code block syntax highlighting tags
- Convert internal links to wiki format
- Fix image paths and references
- Convert Docusaurus admonitions to MediaWiki templates
- Add category assignments based on path

Usage:
    python postprocess.py <wiki_file> [source_md_file]
"""

import csv
import re
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def extract_frontmatter_from_source(source_path: str) -> Dict:
    """Extract YAML frontmatter from original markdown source."""
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                return yaml.safe_load(parts[1]) or {}
    except Exception:
        pass
    return {}


LANG_MAPPINGS = {
    'bash': 'bash',
    'sh': 'bash',
    'shell': 'bash',
    'javascript': 'javascript',
    'js': 'javascript',
    'typescript': 'typescript',
    'ts': 'typescript',
    'python': 'python',
    'py': 'python',
    'php': 'php',
    'json': 'json',
    'yaml': 'yaml',
    'yml': 'yaml',
    'sql': 'sql',
    'nginx': 'nginx',
    'apache': 'apache',
    'xml': 'xml',
    'html': 'html',
    'css': 'css',
    'ini': 'ini',
    'conf': 'ini',
    'env': 'bash',
    'dockerfile': 'docker',
    'plaintext': 'text',
    'text': 'text',
}


def _normalize_lang(lang: str) -> str:
    """Map a language identifier to a canonical name for syntaxhighlight."""
    return LANG_MAPPINGS.get(lang.lower().strip(), lang.lower().strip() or 'text')


def _looks_like_code(text: str) -> bool:
    """Heuristic: does this <pre> block contain actual code rather than prose?"""
    lines = text.strip().splitlines()
    if not lines:
        return False
    code_indicators = 0
    for line in lines:
        stripped = line.strip()
        # Shell commands, variable assignments, braces, imports, etc.
        if re.match(r'^[\$#>]', stripped):
            code_indicators += 1
        elif re.match(r'^(import |from |use |require |include )', stripped):
            code_indicators += 1
        elif re.search(r'[{};=\[\]()]\s*$', stripped):
            code_indicators += 1
        elif re.match(r'^(docker|git|curl|npm|pip|apt|sudo|cd |mkdir|cp |mv |rm |ls |cat |php |python)', stripped):
            code_indicators += 1
        elif re.match(r'^\s*"[\w]+":\s', stripped):  # JSON-like
            code_indicators += 1
        elif re.match(r'^[\w_]+=', stripped):  # env var assignment
            code_indicators += 1
    return code_indicators >= max(1, len(lines) * 0.3)


def fix_code_blocks(content: str) -> str:
    """
    Fix code block syntax highlighting.

    Pandoc produces several patterns we need to handle:
    1. <pre>```lang ... ```</pre>  — fenced code that got wrapped in <pre>
    2. <pre>code...</pre>         — indented code blocks (no fences)
    3. <syntaxhighlight lang="x">  — already correct, just normalize lang
    """
    # Pattern 1: <pre>```lang\n...\n```</pre>  (fenced code inside pre)
    def replace_fenced_in_pre(match):
        lang = match.group(1) or ''
        code = match.group(2)
        lang = _normalize_lang(lang)
        return f'<syntaxhighlight lang="{lang}">\n{code}\n</syntaxhighlight>'

    content = re.sub(
        r'<pre>```(\w*)\n(.*?)\n```</pre>',
        replace_fenced_in_pre,
        content,
        flags=re.DOTALL
    )

    # Pattern 2: standalone ``` blocks that Pandoc left as-is (not in <pre>)
    def replace_bare_fenced(match):
        lang = match.group(1) or ''
        code = match.group(2)
        lang = _normalize_lang(lang)
        return f'<syntaxhighlight lang="{lang}">\n{code}\n</syntaxhighlight>'

    content = re.sub(
        r'^```(\w*)\n(.*?)\n```$',
        replace_bare_fenced,
        content,
        flags=re.DOTALL | re.MULTILINE
    )

    # Pattern 3: <pre> blocks that contain code (heuristic conversion)
    # Only convert if the content looks like code, not prose
    def replace_pre_code(match):
        inner = match.group(1)
        # Don't touch <pre> blocks that contain wiki markup, images, or templates
        if '[[File:' in inner or '{{' in inner or '![' in inner:
            return match.group(0)
        if _looks_like_code(inner):
            lang = _guess_lang(inner)
            return f'<syntaxhighlight lang="{lang}">\n{inner.strip()}\n</syntaxhighlight>'
        return match.group(0)

    content = re.sub(
        r'<pre>(.*?)</pre>',
        replace_pre_code,
        content,
        flags=re.DOTALL
    )

    # Pattern 4: normalize existing syntaxhighlight lang attributes
    def normalize_sh_lang(match):
        lang = _normalize_lang(match.group(1))
        return f'<syntaxhighlight lang="{lang}">'

    content = re.sub(
        r'<syntaxhighlight lang="([^"]*?)">',
        normalize_sh_lang,
        content
    )

    return content


def _guess_lang(code: str) -> str:
    """Try to guess the language of a code block from its content."""
    first_line = code.strip().splitlines()[0] if code.strip() else ''

    # PHP
    if '<?php' in code or re.search(r'\$\w+\s*=\s*\$', code):
        return 'php'
    # JSON
    if re.match(r'\s*[\[{]', code) and re.search(r'["\']\w+["\']\s*:', code):
        return 'json'
    # SQL
    if re.match(r'\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|SET GLOBAL|mysql>)', code, re.IGNORECASE):
        return 'sql'
    # Shell commands
    if re.match(r'\s*[\$#>]', first_line) or re.match(r'\s*(docker|git|curl|npm|sudo|apt|pip|cd |ssh )', first_line):
        return 'bash'
    # YAML/config
    if re.match(r'\w+:\s', first_line):
        return 'yaml'
    # Env vars
    if re.match(r'^[A-Z_]+=', first_line):
        return 'bash'

    return 'text'


def _load_link_mapping(inventory_path: Optional[str] = None) -> Dict[str, str]:
    """
    Build a mapping from source file paths (and their slug variants) to wiki page titles
    using the migration inventory CSV.
    """
    mapping = {}
    if not inventory_path:
        # Try default location
        inventory_path = str(Path(__file__).parent / 'migration_inventory.csv')

    inv_path = Path(inventory_path)
    if not inv_path.exists():
        return mapping

    with open(inv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            source = row.get('source_path', '')
            target = row.get('target_wiki_page', '')
            if not source or not target:
                continue

            # Strip prefix directories to get the relative doc path
            # df-docs/df-docs/docs/getting-started/.../docker-installation.md
            # -> getting-started/.../docker-installation
            for prefix in ['df-docs/df-docs/docs/', 'guide/dreamfactory-book-v2/content/en/docs/']:
                if source.startswith(prefix):
                    source = source[len(prefix):]
                    break

            # Remove .md extension
            source_no_ext = re.sub(r'\.md$', '', source)

            # Store multiple lookup keys for the same target:
            # 1. Full relative path: getting-started/installing-dreamfactory/docker-installation
            mapping[source_no_ext.lower()] = target
            # 2. Just the filename slug: docker-installation
            slug = Path(source_no_ext).stem
            if slug and slug != '_index' and slug not in mapping:
                mapping[slug.lower()] = target
            # 3. With /docs/ prefix (some links use absolute paths)
            mapping[('docs/' + source_no_ext).lower()] = target

    return mapping


# Module-level cache for link mapping
_LINK_MAP: Optional[Dict[str, str]] = None


def _get_link_map() -> Dict[str, str]:
    global _LINK_MAP
    if _LINK_MAP is None:
        _LINK_MAP = _load_link_mapping()
    return _LINK_MAP


def convert_internal_links(content: str, source_path: Optional[str] = None) -> str:
    """
    Convert internal markdown links to MediaWiki links.
    Uses inventory CSV for path→page mapping when available.
    """
    link_map = _get_link_map()

    def replace_link(match):
        text = match.group(1)
        url = match.group(2)

        # External links stay as external
        if url.startswith(('http://', 'https://', 'mailto:')):
            return f'[{url} {text}]'

        # Anchor links
        if url.startswith('#'):
            anchor = url[1:].replace('-', '_')
            return f'[[#{anchor}|{text}]]'

        # Split off any anchor from the path
        anchor_part = ''
        if '#' in url:
            url, anchor_suffix = url.split('#', 1)
            anchor_part = '#' + anchor_suffix.replace('-', '_')

        # Internal links - try inventory mapping first
        path = url.lstrip('/')
        path = re.sub(r'\.md$', '', path)
        path_lower = path.lower()

        # Try various lookup keys
        wiki_page = (link_map.get(path_lower) or
                     link_map.get(Path(path_lower).stem) or
                     link_map.get('docs/' + path_lower))

        if not wiki_page:
            # Fallback: convert path to wiki page format
            parts = path.split('/')
            wiki_page = '/'.join(
                '_'.join(word.capitalize() for word in part.replace('-', '_').split('_'))
                for part in parts if part
            )

        return f'[[{wiki_page}{anchor_part}|{text}]]'

    # Match markdown links: [text](url)
    content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_link, content)

    # Also fix wiki-style internal links that Pandoc already converted
    # [[source/path/page|text]] -> [[Wiki_Page_Title|text]]
    # Skip File:, Category:, #anchor, and already-correct links
    def fix_wiki_link(match):
        target = match.group(1)
        rest = match.group(2)  # |text]] or just ]]

        # Don't touch special namespaces or anchors
        if target.startswith(('File:', 'Category:', '#', 'http', 'Template:')):
            return match.group(0)
        # Don't touch if it has a namespace prefix like V2: or Legacy:
        if re.match(r'^[A-Z][a-z0-9]+:', target):
            return match.group(0)

        # Split off anchor
        anchor_part = ''
        if '#' in target:
            target, anchor_suffix = target.split('#', 1)
            anchor_part = '#' + anchor_suffix.replace('-', '_')

        target_lower = target.lower().strip('/')
        # Try inventory mapping
        wiki_page = (link_map.get(target_lower) or
                     link_map.get(Path(target_lower).stem) or
                     link_map.get('docs/' + target_lower))

        if wiki_page:
            return f'[[{wiki_page}{anchor_part}{rest}'
        return match.group(0)

    content = re.sub(
        r'\[\[([^\]|]+)(\|[^\]]*\]\]|\]\])',
        fix_wiki_link,
        content
    )

    return content


def fix_image_references(content: str) -> str:
    """
    Fix image references for MediaWiki.
    Convert various image syntaxes to [[File:name|options]]
    """
    # Pattern 1: Raw markdown images that Pandoc left unconverted
    # ![alt text](/path/to/image.png)  — sometimes inside <pre> blocks
    def replace_md_image(match):
        alt = match.group(1) or ''
        img_path = match.group(2)
        filename = Path(img_path).name
        if alt:
            return f'[[File:{filename}|thumb|{alt}]]'
        return f'[[File:{filename}|thumb]]'

    content = re.sub(
        r'!\[([^\]]*)\]\(([^)]+)\)',
        replace_md_image,
        content
    )

    # Pattern 2: Pandoc's wiki-style image output with full paths
    # [[File:/img/docker-install/image.png|alt]] -> [[File:image.png|thumb|alt]]
    def fix_wiki_image(match):
        full_path = match.group(1)
        rest = match.group(2) if match.group(2) else ''

        filename = Path(full_path).name

        # Parse existing options
        parts = [p.strip() for p in rest.split('|') if p.strip()] if rest else []
        has_thumb = any(p in ('thumb', 'thumbnail', 'frame', 'frameless') for p in parts)

        if not has_thumb:
            parts.insert(0, 'thumb')

        return f'[[File:{filename}|{"|".join(parts)}]]' if parts else f'[[File:{filename}|thumb]]'

    content = re.sub(
        r'\[\[File:([^\]|]+)\|?([^\]]*)\]\]',
        fix_wiki_image,
        content
    )

    # Pattern 3: Hugo-style HTML images
    # <img src="/images/salesforce/foo.png" width="600" alt="Description">
    def replace_html_image(match):
        attrs = match.group(1)
        src_match = re.search(r'src="([^"]+)"', attrs)
        alt_match = re.search(r'alt="([^"]+)"', attrs)
        if not src_match:
            return match.group(0)
        filename = Path(src_match.group(1)).name
        alt = alt_match.group(1) if alt_match else ''
        if alt:
            return f'[[File:{filename}|thumb|{alt}]]'
        return f'[[File:{filename}|thumb]]'

    content = re.sub(
        r'<img\s+(.*?)/?>',
        replace_html_image,
        content,
        flags=re.DOTALL
    )

    # Clean up: remove <p> tags that wrapped images (from Hugo)
    content = re.sub(r'<p>\s*(\[\[File:.*?\]\])\s*</p>', r'\1', content)

    return content


def convert_admonitions(content: str) -> str:
    """
    Convert Docusaurus admonitions and Hugo alert shortcodes to MediaWiki templates.

    Handles:
    - :::note ... :::              (Docusaurus, bare)
    - <pre>:::caution ...\n::::</pre>  (Docusaurus, wrapped in <pre> by Pandoc)
    - {{< alert color="warning" >}} ... {{< /alert >}}  (Hugo)
    """
    admonition_types = {
        'note': 'Note',
        'warning': 'Warning',
        'tip': 'Tip',
        'info': 'Note',
        'caution': 'Warning',
        'danger': 'Warning',
        'success': 'Tip',
    }

    # Pattern 1: Docusaurus admonitions wrapped in <pre> by Pandoc
    # <pre>:::type Title\ncontent\n::::</pre>  (:::: is how Pandoc renders the closing :::)
    # Handles: :::tip Pro Tip (space-separated title)
    #          :::info[CLI Methods] (bracket-enclosed title)
    for admon_type, template in admonition_types.items():
        pattern = rf'<pre>\s*:::{admon_type}(?:\[([^\]]*)\]|\s+([^\n]*?))?\s*\n(.*?)\s*::::?\s*</pre>'
        def make_replacement(template_name):
            def replacer(match):
                bracket_title = match.group(1)  # from :::type[Title]
                space_title = match.group(2)     # from :::type Title
                body = match.group(3).strip()
                title = (bracket_title or space_title or '').strip()
                if title:
                    return f'{{{{{template_name}|title={title}|{body}}}}}'
                return f'{{{{{template_name}|{body}}}}}'
            return replacer
        content = re.sub(pattern, make_replacement(template), content,
                         flags=re.DOTALL | re.IGNORECASE)

    # Pattern 2: Bare Docusaurus admonitions (not wrapped in <pre>)
    # Handles: :::tip Pro Tip (space-separated title)
    #          :::info[CLI Methods] (bracket-enclosed title)
    for admon_type, template in admonition_types.items():
        pattern = rf':::{admon_type}(?:\[([^\]]*)\]|\s+([^\n]*?))?\s*\n(.*?)\s*:::(?!:)'
        def make_replacement2(template_name):
            def replacer(match):
                bracket_title = match.group(1)  # from :::type[Title]
                space_title = match.group(2)     # from :::type Title
                body = match.group(3).strip()
                title = (bracket_title or space_title or '').strip()
                if title:
                    return f'{{{{{template_name}|title={title}|{body}}}}}'
                return f'{{{{{template_name}|{body}}}}}'
            return replacer
        content = re.sub(pattern, make_replacement2(template), content,
                         flags=re.DOTALL | re.IGNORECASE)

    # Pattern 3: Hugo alert shortcodes
    # {{< alert color="warning" title="Warning" >}} ... {{< /alert >}}
    # Also handles {{%  %}} variant
    # Note: Pandoc converts straight quotes to curly/smart quotes (U+201C/U+201D)
    def replace_hugo_alert(match):
        attrs = match.group(1)
        body = match.group(2).strip()
        # Extract color/type — handle both straight and curly quotes
        color_match = re.search(r'color=["\u201c](\w+)["\u201d]', attrs)
        color = color_match.group(1) if color_match else 'note'
        template = admonition_types.get(color.lower(), 'Note')
        return f'{{{{{template}|{body}}}}}'

    content = re.sub(
        r'\{\{[<%]\s*alert\s+(.*?)\s*[>%]\}\}(.*?)\{\{[<%]\s*/alert\s*[>%]\}\}',
        replace_hugo_alert,
        content,
        flags=re.DOTALL
    )

    # Pattern 4: HTML-escaped Hugo shortcodes (Pandoc sometimes escapes the braces)
    content = re.sub(
        r'\{\{&lt;\s*alert\s+(.*?)\s*&gt;\}\}(.*?)\{\{&lt;\s*/alert\s*&gt;\}\}',
        replace_hugo_alert,
        content,
        flags=re.DOTALL
    )

    return content


def extract_frontmatter_from_hugo(source_path: str) -> Dict:
    """Extract frontmatter from Hugo markdown (TOML +++ or YAML --- format)."""
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # YAML frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                return yaml.safe_load(parts[1]) or {}

        # TOML frontmatter
        if content.startswith('+++'):
            parts = content.split('+++', 2)
            if len(parts) >= 3:
                # Simple TOML key=value parsing (no dependency on toml package)
                result = {}
                for line in parts[1].strip().splitlines():
                    line = line.strip()
                    if '=' in line:
                        key, _, val = line.partition('=')
                        val = val.strip().strip('"').strip("'")
                        result[key.strip()] = val
                return result
    except Exception:
        pass
    return {}


def add_categories(content: str, frontmatter: Dict, source_path: Optional[str] = None) -> str:
    """
    Add MediaWiki categories based on frontmatter and source path.
    """
    categories = []

    # Add categories based on keywords
    keywords = frontmatter.get('keywords', [])
    if isinstance(keywords, list):
        for keyword in keywords[:3]:  # Limit to first 3 keywords
            cat = keyword.strip().replace(' ', '_').title()
            if len(cat) > 2:
                categories.append(cat)

    # Add categories based on source path
    if source_path:
        path_lower = source_path.lower()
        if 'security' in path_lower or 'securing' in path_lower:
            categories.append('Security')
        if 'installation' in path_lower or 'installing' in path_lower:
            categories.append('Installation')
        if 'getting-started' in path_lower:
            categories.append('Getting_Started')
        if 'api' in path_lower:
            categories.append('API')
        if 'database' in path_lower:
            categories.append('Database')
        if 'scripting' in path_lower:
            categories.append('Scripting')
        if 'upgrade' in path_lower or 'migration' in path_lower:
            categories.append('Upgrades')
        if 'salesforce' in path_lower:
            categories.append('Salesforce')
        if 'file' in path_lower and 'storage' in path_lower:
            categories.append('File_Storage')
        # Guide/Hugo source marker
        if 'guide/' in path_lower or 'dreamfactory-book' in path_lower:
            categories.append('Legacy_Guide')

    # Add difficulty-based category
    difficulty = frontmatter.get('difficulty', '')
    if difficulty:
        categories.append(f'Difficulty_{difficulty.capitalize()}')

    # Hugo title-based fallback when no keywords
    if not keywords and frontmatter.get('title'):
        title = frontmatter['title']
        # Extract meaningful words from title
        words = [w for w in re.split(r'\s+', title) if len(w) > 3 and w[0].isupper()]
        for word in words[:2]:
            categories.append(word.replace(' ', '_'))

    # Deduplicate and add to content
    categories = list(dict.fromkeys(categories))

    if categories:
        category_text = '\n'.join(f'[[Category:{cat}]]' for cat in categories)
        content = content.rstrip() + '\n\n' + category_text + '\n'

    return content


def add_page_metadata(content: str, frontmatter: Dict) -> str:
    """
    Add metadata section at the top of the page.
    """
    metadata_parts = []

    title = frontmatter.get('title', '')
    if title:
        # Don't add redundant title if content already starts with it
        if not content.strip().startswith(f'= {title} ='):
            metadata_parts.append(f'= {title} =')

    description = frontmatter.get('description', '')
    if description:
        metadata_parts.append(f"'''{description}'''")
        metadata_parts.append('')

    if metadata_parts:
        return '\n'.join(metadata_parts) + '\n' + content

    return content


def extract_content_from_pre_blocks(content: str) -> str:
    """
    Pre-pass: extract images, admonitions, and other wiki content
    that Pandoc incorrectly wrapped inside <pre> blocks.

    This must run BEFORE fix_code_blocks so these elements aren't
    treated as code.
    """
    def process_pre(match):
        inner = match.group(1)

        # If the <pre> contains admonitions, extract them
        if re.search(r':::(note|warning|tip|caution|info|danger)', inner, re.IGNORECASE):
            # Return without <pre> wrapper — admonition handler will process it
            return inner

        # If the <pre> contains markdown images, extract them and keep the rest
        if '![' in inner and '](' in inner:
            # Split into image and non-image parts
            parts = re.split(r'(!\[[^\]]*\]\([^)]+\))', inner)
            result_parts = []
            text_parts = []
            for part in parts:
                if re.match(r'^!\[', part):
                    # Flush accumulated text as <pre> if it has content
                    if text_parts and ''.join(text_parts).strip():
                        result_parts.append(f'<pre>{"".join(text_parts)}</pre>')
                    text_parts = []
                    # Image goes outside <pre>
                    result_parts.append(part)
                else:
                    text_parts.append(part)
            if text_parts and ''.join(text_parts).strip():
                result_parts.append(f'<pre>{"".join(text_parts)}</pre>')
            return '\n'.join(result_parts)

        # No special content, leave as-is
        return match.group(0)

    content = re.sub(r'<pre>(.*?)</pre>', process_pre, content, flags=re.DOTALL)
    return content


def clean_pandoc_artifacts(content: str) -> str:
    """
    Clean up common Pandoc conversion artifacts.
    """
    # Remove excessive blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)

    # Fix broken table syntax
    content = re.sub(r'\{\|class=', r'{| class=', content)

    # Remove <div> tags that Pandoc sometimes adds
    content = re.sub(r'<div[^>]*>\s*', '', content)
    content = re.sub(r'\s*</div>', '', content)

    # Fix escaped characters
    content = content.replace(r'\[', '[')
    content = content.replace(r'\]', ']')
    content = content.replace(r'\|', '|')

    # Normalize curly/smart quotes to straight quotes (Pandoc's --smart option)
    content = content.replace('\u201c', '"')  # Left double quotation mark
    content = content.replace('\u201d', '"')  # Right double quotation mark
    content = content.replace('\u2018', "'")  # Left single quotation mark
    content = content.replace('\u2019', "'")  # Right single quotation mark

    return content


def _load_inventory_data(inventory_path: Optional[str] = None) -> Tuple[List[Dict], set]:
    """Load inventory rows and return (all_rows, skip_sources set)."""
    if not inventory_path:
        inventory_path = str(Path(__file__).parent / 'migration_inventory.csv')
    inv_path = Path(inventory_path)
    if not inv_path.exists():
        return [], set()
    with open(inv_path, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    skip_sources = set()
    for row in rows:
        if row.get('status', '') == 'Skip-EmptyDraft':
            src = row.get('source_path', '')
            if src:
                skip_sources.add(src)
    return rows, skip_sources


def add_see_also_section(
    content: str,
    source_path: Optional[str] = None,
    inventory_path: Optional[str] = None,
) -> str:
    """
    Add a == See also == section with internal links if the page is under-linked.

    Strategy:
    1. Count existing internal wiki links ([[Page|text]])
    2. If below threshold (4 for leaf pages, 25 for hubs), generate See also links
    3. Links to: parent hub page, sibling pages (same directory), keyword-related pages
    4. Exclude pages marked Skip-EmptyDraft in inventory
    5. Insert before [[Category:]] tags at the end
    """
    # Count existing internal links (wiki-style)
    existing_links = re.findall(r'\[\[(?!Category:|File:|#)([^\]|]+)', content)
    existing_count = len(existing_links)
    existing_targets = {link.strip().lower() for link in existing_links}

    # Determine if this is a hub page (heuristic: has many links or is _index)
    is_hub = existing_count > 15
    if source_path:
        stem = Path(source_path).stem.lower()
        if stem in ('index', '_index', 'introduction'):
            is_hub = True

    threshold = 25 if is_hub else 4
    if existing_count >= threshold:
        return content  # Already well-linked

    # Load inventory to find related pages
    rows, skip_sources = _load_inventory_data(inventory_path)
    if not rows:
        return content

    # Determine this page's wiki target and directory context
    link_map = _get_link_map()
    current_target = None
    current_dir = None

    if source_path:
        # Resolve to absolute then extract relative doc path
        resolved = str(Path(source_path).resolve())
        src_key = resolved
        for marker in ['df-docs/df-docs/docs/', 'guide/dreamfactory-book-v2/content/en/docs/']:
            idx = src_key.find(marker)
            if idx >= 0:
                src_key = src_key[idx + len(marker):]
                break
        src_no_ext = re.sub(r'\.md$', '', src_key)
        current_target = link_map.get(src_no_ext.lower()) or link_map.get(Path(src_no_ext).stem.lower())
        current_dir = str(Path(src_key).parent)

    # Collect candidate pages
    see_also_links: List[Tuple[str, str]] = []  # (wiki_page, display_title)

    # Find parent hub page
    if current_target and '/' in current_target:
        parent_target = '/'.join(current_target.split('/')[:-1])
        for row in rows:
            if row.get('source_path', '') in skip_sources:
                continue
            if row.get('target_wiki_page', '') == parent_target:
                title = row.get('title', parent_target)
                if parent_target.lower() not in existing_targets:
                    see_also_links.append((parent_target, title))
                break

    # Helper: extract relative doc path from an inventory source_path
    def _rel_doc_path(inv_src: str) -> str:
        for pfx in ['df-docs/df-docs/docs/', 'guide/dreamfactory-book-v2/content/en/docs/']:
            if inv_src.startswith(pfx):
                return inv_src[len(pfx):]
        return inv_src

    # Find sibling pages (same directory in source)
    if current_dir:
        for row in rows:
            src = row.get('source_path', '')
            if src in skip_sources:
                continue
            target = row.get('target_wiki_page', '')
            title = row.get('title', '')
            if not target or not title:
                continue
            row_dir = str(Path(_rel_doc_path(src)).parent)
            if row_dir == current_dir and target != current_target:
                if target.lower() not in existing_targets:
                    see_also_links.append((target, title))

    # Find keyword-related pages (share keywords from inventory)
    current_keywords = set()
    current_src_rel = None
    if source_path:
        resolved = str(Path(source_path).resolve())
        for marker in ['df-docs/df-docs/docs/', 'guide/dreamfactory-book-v2/content/en/docs/']:
            idx = resolved.find(marker)
            if idx >= 0:
                current_src_rel = resolved[idx:]
                break
        for row in rows:
            row_src = row.get('source_path', '')
            if row_src == current_src_rel or (current_src_rel and current_src_rel.endswith(row_src)):
                kw = row.get('keywords', '')
                if kw:
                    current_keywords = {k.strip().lower() for k in kw.split(',') if k.strip()}
                break

    if current_keywords:
        for row in rows:
            src = row.get('source_path', '')
            if src in skip_sources or src == source_path:
                continue
            target = row.get('target_wiki_page', '')
            title = row.get('title', '')
            if not target or not title:
                continue
            row_kw = row.get('keywords', '')
            if row_kw:
                row_keywords = {k.strip().lower() for k in row_kw.split(',') if k.strip()}
                overlap = current_keywords & row_keywords
                if len(overlap) >= 2 and target.lower() not in existing_targets:
                    see_also_links.append((target, title))

    # Deduplicate while preserving order
    seen = set()
    unique_links = []
    for target, title in see_also_links:
        key = target.lower()
        if key not in seen:
            seen.add(key)
            unique_links.append((target, title))

    # Limit to a reasonable number
    needed = threshold - existing_count
    unique_links = unique_links[:max(needed, 3)]

    if not unique_links:
        return content

    # Build See also section
    see_also_lines = ['\n== See also ==']
    for target, title in unique_links:
        see_also_lines.append(f'* [[{target}|{title}]]')

    see_also_text = '\n'.join(see_also_lines) + '\n'

    # Insert before [[Category:]] tags at the end, or append
    category_match = re.search(r'\n\[\[Category:', content)
    if category_match:
        insert_pos = category_match.start()
        content = content[:insert_pos] + '\n' + see_also_text + content[insert_pos:]
    else:
        content = content.rstrip() + '\n' + see_also_text

    return content


def postprocess_wiki_file(wiki_path: str, source_path: Optional[str] = None) -> bool:
    """
    Apply all post-processing fixes to a wiki file.

    Processing order matters:
    1. Clean Pandoc artifacts
    2. Extract images/admonitions trapped in <pre> blocks
    3. Convert admonitions (Docusaurus + Hugo)
    4. Fix image references (markdown, wiki, HTML)
    5. Fix code blocks (<pre> → syntaxhighlight)
    6. Convert internal links (using inventory mapping)
    7. Add categories
    8. Add page metadata (title, description)
    """
    try:
        with open(wiki_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Get frontmatter from source if available
        frontmatter = {}
        if source_path:
            frontmatter = extract_frontmatter_from_source(source_path)
            # Fall back to Hugo-style frontmatter
            if not frontmatter:
                frontmatter = extract_frontmatter_from_hugo(source_path)

        # Apply fixes in order (order matters!)
        content = clean_pandoc_artifacts(content)
        content = extract_content_from_pre_blocks(content)  # Must be before code blocks
        content = convert_admonitions(content)               # Must be before code blocks
        content = fix_image_references(content)              # Must be before code blocks
        content = fix_code_blocks(content)
        content = convert_internal_links(content, source_path)
        content = add_see_also_section(content, source_path)
        content = add_categories(content, frontmatter, source_path)
        content = add_page_metadata(content, frontmatter)

        # Write back
        with open(wiki_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return True

    except Exception as e:
        print(f"Error processing {wiki_path}: {e}", file=sys.stderr)
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python postprocess.py <wiki_file> [source_md_file]")
        sys.exit(1)

    wiki_path = sys.argv[1]
    source_path = sys.argv[2] if len(sys.argv) > 2 else None

    success = postprocess_wiki_file(wiki_path, source_path)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
