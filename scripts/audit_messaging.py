#!/usr/bin/env python3
"""
Audit wiki pages on staging MediaWiki for outdated DreamFactory messaging.

Golden anchor statements:
- Short: "DreamFactory is a self-hosted platform providing governed API access
         to any data source for enterprise apps and local LLMs."
- Long:  "DreamFactory is a secure, self-hosted enterprise data access platform
         that provides governed API access to any data source, connecting
         enterprise applications and on-prem LLMs with role-based access and
         identity passthrough."

This script fetches ALL pages, searches for positioning/descriptive statements
about DreamFactory, and flags lines that don't align with the golden anchors.
"""

import re
import mwclient
import textwrap

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WIKI_HOST = "localhost:8082"
SCHEME = "http"

# Patterns that identify a positioning / descriptive statement about DF
DESCRIPTOR_PATTERNS = [
    re.compile(r"DreamFactory\s+is\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+provides\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+enables\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+allows\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+generates?\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+platform\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+offers?\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+makes?\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+can\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+helps?\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+serves?\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+acts?\b", re.IGNORECASE),
    re.compile(r"DreamFactory\s+works?\b", re.IGNORECASE),
    re.compile(r"DreamFactory,?\s+a[n]?\s+", re.IGNORECASE),  # "DreamFactory, a ..."
]

# Known outdated / misaligned phrases
OUTDATED_PHRASES = [
    re.compile(r"open[\-\s]source\s+(REST\s+)?API", re.IGNORECASE),
    re.compile(r"REST\s+API\s+automation", re.IGNORECASE),
    re.compile(r"API\s+automation\s+platform", re.IGNORECASE),
    re.compile(r"API\s+management\s+platform", re.IGNORECASE),
    re.compile(r"instant\s+API\s+generation", re.IGNORECASE),
    re.compile(r"instant\s+API", re.IGNORECASE),
    re.compile(r"auto[\-\s]?generat\w+\s+API", re.IGNORECASE),
    re.compile(r"automatically\s+generates?\s+.{0,20}API", re.IGNORECASE),
    re.compile(r"open[\-\s]source\s+platform", re.IGNORECASE),
    re.compile(r"API\s+generation\s+platform", re.IGNORECASE),
    re.compile(r"API\s+platform", re.IGNORECASE),
]

# Phrases that indicate alignment with the golden anchor
ALIGNED_PHRASES = [
    re.compile(r"governed\s+API\s+access", re.IGNORECASE),
    re.compile(r"enterprise\s+data\s+access", re.IGNORECASE),
    re.compile(r"self[\-\s]hosted\s+(enterprise\s+)?.*platform", re.IGNORECASE),
    re.compile(r"governed\s+access", re.IGNORECASE),
    re.compile(r"role[\-\s]based\s+access", re.IGNORECASE),
    re.compile(r"identity\s+passthrough", re.IGNORECASE),
    re.compile(r"enterprise\s+app", re.IGNORECASE),
    re.compile(r"on[\-\s]prem\s+LLM", re.IGNORECASE),
    re.compile(r"local\s+LLM", re.IGNORECASE),
    re.compile(r"any\s+data\s+source", re.IGNORECASE),
]

# Lines that are merely procedural / passing mentions — skip these
SKIP_PATTERNS = [
    re.compile(r"^\s*\|"),                       # table rows
    re.compile(r"install\s+DreamFactory", re.IGNORECASE),
    re.compile(r"DreamFactory\s+admin", re.IGNORECASE),
    re.compile(r"DreamFactory\s+(instance|server|container|docker|image|version|release|package|directory|folder|file)", re.IGNORECASE),
    re.compile(r"DreamFactory\s+\d+\.\d+", re.IGNORECASE),  # version numbers
    re.compile(r"(start|stop|restart|configure|upgrade|update)\s+DreamFactory", re.IGNORECASE),
    re.compile(r"DreamFactory\s+(UI|dashboard|interface|console|panel|page|tab|screen|menu|sidebar)", re.IGNORECASE),
    re.compile(r"log\s+into\s+DreamFactory", re.IGNORECASE),
    re.compile(r"DreamFactory\s+(user|account|login|password|email)", re.IGNORECASE),
    re.compile(r"DreamFactory\s+documentation", re.IGNORECASE),
    re.compile(r"^\s*#", re.IGNORECASE),         # headings by themselves
    re.compile(r"^\s*\[\[", re.IGNORECASE),       # wikilinks at line start
    re.compile(r"^\s*<", re.IGNORECASE),          # HTML/template tags
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_sentence_around_match(line: str, match_start: int) -> str:
    """Return the full sentence (or the full line if short) around match_start."""
    line = line.strip()
    if len(line) <= 200:
        return line

    # Try to find sentence boundaries
    # Look backward for sentence start
    start = match_start
    while start > 0 and line[start - 1] not in ".!?\n":
        start -= 1

    # Look forward for sentence end
    end = match_start
    while end < len(line) and line[end] not in ".!?\n":
        end += 1
    if end < len(line):
        end += 1  # include the period

    sentence = line[start:end].strip()
    if len(sentence) < 20:
        # Fallback: return a window around the match
        start = max(0, match_start - 80)
        end = min(len(line), match_start + 120)
        sentence = line[start:end].strip()
        if start > 0:
            sentence = "..." + sentence
        if end < len(line):
            sentence = sentence + "..."

    return sentence


def classify_line(line: str):
    """
    Classify a line as ALIGNED, OUTDATED, or REVIEW_NEEDED.
    Returns (verdict, reasons).
    """
    outdated_hits = []
    for pat in OUTDATED_PHRASES:
        m = pat.search(line)
        if m:
            outdated_hits.append(m.group())

    aligned_hits = []
    for pat in ALIGNED_PHRASES:
        m = pat.search(line)
        if m:
            aligned_hits.append(m.group())

    if outdated_hits and not aligned_hits:
        return "OUTDATED", outdated_hits
    elif outdated_hits and aligned_hits:
        return "MIXED — needs review", outdated_hits + aligned_hits
    elif aligned_hits:
        return "ALIGNED", aligned_hits
    else:
        return "REVIEW NEEDED — no golden anchor language found", []


def should_skip(line: str) -> bool:
    """Return True if the line is a procedural / passing mention."""
    for pat in SKIP_PATTERNS:
        if pat.search(line):
            return True
    return False


def is_descriptor_match(line: str):
    """Check if line contains a positioning/descriptive statement about DF."""
    for pat in DESCRIPTOR_PATTERNS:
        m = pat.search(line)
        if m:
            return m
    return None


def check_first_lines(text: str, page_title: str):
    """
    Also check the first ~5 non-empty, non-heading lines for any DF mentions,
    since intros often describe the product.
    """
    results = []
    count = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("=") or stripped.startswith("__") or stripped.startswith("[[Category"):
            continue
        count += 1
        if count > 5:
            break
        if re.search(r"DreamFactory", stripped, re.IGNORECASE):
            results.append(stripped)
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("DREAMFACTORY MESSAGING AUDIT — Staging Wiki")
    print("=" * 80)
    print()
    print("Golden anchor (short):")
    print("  DreamFactory is a self-hosted platform providing governed API access")
    print("  to any data source for enterprise apps and local LLMs.")
    print()
    print("Golden anchor (long):")
    print("  DreamFactory is a secure, self-hosted enterprise data access platform")
    print("  that provides governed API access to any data source, connecting")
    print("  enterprise applications and on-prem LLMs with role-based access and")
    print("  identity passthrough.")
    print()
    print("-" * 80)
    print()

    # Connect — the staging wiki has its API at /api.php (no /w/ prefix)
    site = mwclient.Site(WIKI_HOST, scheme=SCHEME, path="/")
    site.force_login = False

    pages_checked = 0
    findings = []  # list of dicts

    for page in site.allpages():
        pages_checked += 1
        title = page.page_title
        text = page.text()

        if not text or not text.strip():
            continue

        # Track matches for this page to avoid duplicates
        seen_lines = set()

        lines = text.split("\n")
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue

            # Check for descriptor patterns
            m = is_descriptor_match(stripped)
            if not m:
                # Also check for outdated phrases even without a descriptor pattern
                has_outdated = False
                for pat in OUTDATED_PHRASES:
                    if pat.search(stripped):
                        has_outdated = True
                        break
                if not has_outdated:
                    continue

            # Skip procedural mentions
            if should_skip(stripped):
                continue

            # De-duplicate
            norm = stripped[:120]
            if norm in seen_lines:
                continue
            seen_lines.add(norm)

            # Extract the relevant sentence
            if m:
                sentence = extract_sentence_around_match(stripped, m.start())
            else:
                sentence = stripped[:200]

            verdict, reasons = classify_line(stripped)

            findings.append({
                "page": title,
                "line_num": line_num,
                "sentence": sentence,
                "verdict": verdict,
                "reasons": reasons,
            })

        # Also check first lines for intro-level product descriptions
        intro_lines = check_first_lines(text, title)
        for intro_line in intro_lines:
            norm = intro_line[:120]
            if norm in seen_lines:
                continue
            seen_lines.add(norm)

            if should_skip(intro_line):
                continue

            # Only include if it looks like a product description
            has_df_descriptor = is_descriptor_match(intro_line)
            has_outdated = any(p.search(intro_line) for p in OUTDATED_PHRASES)
            if not has_df_descriptor and not has_outdated:
                continue

            verdict, reasons = classify_line(intro_line)
            findings.append({
                "page": title,
                "line_num": "intro",
                "sentence": intro_line[:200],
                "verdict": verdict,
                "reasons": reasons,
            })

    # ---------------------------------------------------------------------------
    # Report
    # ---------------------------------------------------------------------------
    # Separate into buckets
    outdated = [f for f in findings if f["verdict"] == "OUTDATED"]
    mixed = [f for f in findings if "MIXED" in f["verdict"]]
    review = [f for f in findings if "REVIEW NEEDED" in f["verdict"]]
    aligned = [f for f in findings if f["verdict"] == "ALIGNED"]

    def print_finding(f, idx):
        print(f"  {idx}. Page: [[{f['page']}]]  (line {f['line_num']})")
        wrapped = textwrap.fill(f["sentence"], width=76, initial_indent="     Text: ",
                                subsequent_indent="           ")
        print(wrapped)
        print(f"     Verdict: {f['verdict']}")
        if f["reasons"]:
            print(f"     Matched: {', '.join(f['reasons'])}")
        print()

    # --- OUTDATED ---
    print(f"{'=' * 80}")
    print(f"  OUTDATED — Needs Rewriting  ({len(outdated)} found)")
    print(f"{'=' * 80}")
    print()
    if outdated:
        for i, f in enumerate(outdated, 1):
            print_finding(f, i)
    else:
        print("  (none)")
        print()

    # --- MIXED ---
    print(f"{'=' * 80}")
    print(f"  MIXED — Has Both Old and New Language  ({len(mixed)} found)")
    print(f"{'=' * 80}")
    print()
    if mixed:
        for i, f in enumerate(mixed, 1):
            print_finding(f, i)
    else:
        print("  (none)")
        print()

    # --- REVIEW NEEDED ---
    print(f"{'=' * 80}")
    print(f"  REVIEW NEEDED — Describes DF but Missing Anchor Language  ({len(review)} found)")
    print(f"{'=' * 80}")
    print()
    if review:
        for i, f in enumerate(review, 1):
            print_finding(f, i)
    else:
        print("  (none)")
        print()

    # --- ALIGNED ---
    print(f"{'=' * 80}")
    print(f"  ALIGNED — Matches Golden Anchor  ({len(aligned)} found)")
    print(f"{'=' * 80}")
    print()
    if aligned:
        for i, f in enumerate(aligned, 1):
            print_finding(f, i)
    else:
        print("  (none)")
        print()

    # --- Summary ---
    print(f"{'=' * 80}")
    print(f"  SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Total pages scanned:        {pages_checked}")
    print(f"  Total findings:             {len(findings)}")
    print(f"  ----")
    print(f"  OUTDATED (needs rewrite):   {len(outdated)}")
    print(f"  MIXED (needs review):       {len(mixed)}")
    print(f"  REVIEW NEEDED (no anchor):  {len(review)}")
    print(f"  ALIGNED (looks good):       {len(aligned)}")
    print()

    # List unique pages that need attention
    pages_needing_work = sorted(set(
        f["page"] for f in findings if f["verdict"] != "ALIGNED"
    ))
    if pages_needing_work:
        print(f"  Pages needing attention ({len(pages_needing_work)}):")
        for p in pages_needing_work:
            print(f"    - [[{p}]]")
    print()


if __name__ == "__main__":
    main()
