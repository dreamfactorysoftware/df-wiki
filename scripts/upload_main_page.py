#!/usr/bin/env python3
"""
upload_main_page.py - Upload Main Page, templates, CSS, and releases to the wiki.

Orchestrates the full Main Page deployment:
1. Upload 6 templates
2. Fetch and upload GitHub releases
3. Append Main Page CSS to MediaWiki:Common.css
4. Upload Main Page content

Usage:
    python upload_main_page.py [--wiki-url URL] [--dry-run]
"""

import argparse
import sys
from pathlib import Path

import mwclient

SCRIPT_DIR = Path(__file__).parent
TEMPLATE_DIR = SCRIPT_DIR / "main_page_templates"

# Template files → wiki page names
TEMPLATES = {
    "NavCard.wiki": "Template:NavCard",
    "ConnectorType.wiki": "Template:ConnectorType",
    "GitHubRelease.wiki": "Template:GitHubRelease",
    "ExternalLink.wiki": "Template:ExternalLink",
    "MainPageSection.wiki": "Template:MainPageSection",
    "DreamFactory_Releases.wiki": "Template:DreamFactory Releases",
}

CSS_MARKER = "/* DreamFactory Main Page Styles */"


def connect(wiki_url):
    """Connect to the wiki and return the site object."""
    url = wiki_url.replace("https://", "").replace("http://", "")
    host = url.split("/")[0]
    path = "/" + "/".join(url.split("/")[1:]) if "/" in url else "/"
    if not path.endswith("/"):
        path += "/"
    scheme = "https" if wiki_url.startswith("https://") else "http"

    site = mwclient.Site(host, path=path, scheme=scheme)
    site.force_login = False
    return site


def upload_templates(site, dry_run=False):
    """Upload all template files to the wiki."""
    print("\n=== Uploading Templates ===")
    count = 0
    for filename, page_name in TEMPLATES.items():
        filepath = TEMPLATE_DIR / filename
        if not filepath.exists():
            print(f"  SKIP {page_name} — file not found: {filepath}")
            continue

        content = filepath.read_text(encoding="utf-8")
        if dry_run:
            print(f"  [DRY RUN] Would upload {page_name}")
        else:
            page = site.pages[page_name]
            page.save(content, summary="Main Page template (automated)")
            status = "Updated" if page.exists else "Created"
            print(f"  {status}: {page_name}")
        count += 1
    print(f"  Templates processed: {count}/{len(TEMPLATES)}")
    return count


def update_releases(site, dry_run=False):
    """Fetch GitHub releases and update the wiki template."""
    print("\n=== Fetching GitHub Releases ===")
    try:
        from update_releases import fetch_releases, format_releases
    except ImportError:
        # Add script dir to path
        sys.path.insert(0, str(SCRIPT_DIR))
        from update_releases import fetch_releases, format_releases

    try:
        releases = fetch_releases(5)
        print(f"  Found {len(releases)} releases")
        for r in releases:
            print(f"    {r['version']} ({r['date']})")

        content = format_releases(releases)
        if dry_run:
            print("  [DRY RUN] Would update Template:DreamFactory Releases")
        else:
            page = site.pages["Template:DreamFactory Releases"]
            page.save(content, summary="Update GitHub releases (automated)")
            print("  Updated Template:DreamFactory Releases")
        return True
    except Exception as e:
        print(f"  WARNING: Could not fetch releases: {e}")
        print("  The releases template will show a placeholder message.")
        return False


def upload_css(site, dry_run=False):
    """Append Main Page CSS to MediaWiki:Common.css if not already present."""
    print("\n=== Uploading Main Page CSS ===")
    css_file = TEMPLATE_DIR / "MainPage.css"
    if not css_file.exists():
        print("  ERROR: MainPage.css not found")
        return False

    new_css = css_file.read_text(encoding="utf-8")

    if dry_run:
        print("  [DRY RUN] Would append CSS to MediaWiki:Common.css")
        return True

    page = site.pages["MediaWiki:Common.css"]
    existing = page.text() if page.exists else ""

    if CSS_MARKER in existing:
        # Replace existing main page CSS block
        start = existing.index(CSS_MARKER)
        end_marker = "/* END DreamFactory Main Page Styles */"
        if end_marker in existing:
            end = existing.index(end_marker) + len(end_marker)
            existing = existing[:start].rstrip() + "\n" + existing[end:].lstrip()
        else:
            existing = existing[:start].rstrip()
        print("  Replacing existing Main Page CSS block")

    # Append new CSS
    if existing.strip():
        combined = existing.rstrip() + "\n\n" + new_css
    else:
        combined = new_css

    page.save(combined, summary="Add/update Main Page styles (automated)")
    print("  Updated MediaWiki:Common.css")
    return True


def upload_main_page(site, dry_run=False):
    """Upload the Main Page content."""
    print("\n=== Uploading Main Page ===")
    content_file = TEMPLATE_DIR / "MainPage.wiki"
    if not content_file.exists():
        print("  ERROR: MainPage.wiki not found")
        return False

    content = content_file.read_text(encoding="utf-8")

    if dry_run:
        print("  [DRY RUN] Would upload Main Page")
        return True

    page = site.pages["Main Page"]
    page.save(content, summary="DreamFactory Main Page (automated)")
    print("  Updated Main Page")
    return True


def main():
    parser = argparse.ArgumentParser(description="Upload DreamFactory Main Page to wiki")
    parser.add_argument("--wiki-url", default="http://localhost:8082",
                        help="MediaWiki URL (default: http://localhost:8082)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate without making changes")
    args = parser.parse_args()

    print(f"Wiki: {args.wiki_url}")
    if args.dry_run:
        print("MODE: DRY RUN")

    site = connect(args.wiki_url)

    results = {}
    results["templates"] = upload_templates(site, args.dry_run)
    results["releases"] = update_releases(site, args.dry_run)
    results["css"] = upload_css(site, args.dry_run)
    results["main_page"] = upload_main_page(site, args.dry_run)

    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"  Templates uploaded: {results['templates']}/{len(TEMPLATES)}")
    print(f"  GitHub releases:    {'OK' if results['releases'] else 'FAILED (placeholder used)'}")
    print(f"  CSS appended:       {'OK' if results['css'] else 'FAILED'}")
    print(f"  Main Page uploaded: {'OK' if results['main_page'] else 'FAILED'}")
    print("=" * 50)

    if not all([results["css"], results["main_page"]]):
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
