#!/usr/bin/env python3
"""
update_releases.py - Fetch GitHub releases and update the wiki template.

Fetches the latest DreamFactory releases from GitHub and uploads them
as {{GitHubRelease}} template calls to Template:DreamFactory Releases.

Usage:
    python update_releases.py [--wiki-url URL] [--dry-run]
"""

import argparse
import re
from datetime import datetime

import requests
import mwclient

GITHUB_API = "https://api.github.com/repos/dreamfactorysoftware/dreamfactory/releases"
DEFAULT_WIKI = "localhost:8082"


def fetch_releases(count=5):
    """Fetch recent releases from GitHub."""
    resp = requests.get(GITHUB_API, params={"per_page": count}, timeout=15)
    resp.raise_for_status()
    releases = []
    for r in resp.json():
        body = r.get("body", "") or ""
        # Take first 2-3 meaningful lines
        lines = [l.strip() for l in body.splitlines() if l.strip() and not l.strip().startswith('#')]
        summary = " ".join(lines[:3])
        # Truncate long summaries
        if len(summary) > 200:
            summary = summary[:197] + "..."
        # Clean markdown formatting for wiki
        summary = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', summary)
        summary = re.sub(r'[*_`]', '', summary)

        date_str = r.get("published_at", "")
        if date_str:
            try:
                date_str = datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        releases.append({
            "version": r.get("tag_name", "unknown"),
            "date": date_str,
            "notes": summary or "See release page for details.",
            "url": r.get("html_url", ""),
        })
    return releases


def format_releases(releases):
    """Format releases as wiki template calls."""
    parts = [
        '<noinclude>Container for DreamFactory release entries. '
        'Updated automatically by update_releases.py.</noinclude><includeonly>'
    ]
    for r in releases:
        parts.append(
            "{{GitHubRelease"
            f"|version={r['version']}"
            f"|date={r['date']}"
            f"|notes={r['notes']}"
            f"|url={r['url']}"
            "}}"
        )
    parts.append('</includeonly>')
    return "\n".join(parts)


def upload_releases(wiki_host, wiki_path, scheme, content, dry_run=False):
    """Upload formatted releases to the wiki."""
    if dry_run:
        print("[DRY RUN] Would upload Template:DreamFactory Releases")
        print(content)
        return True

    site = mwclient.Site(wiki_host, path=wiki_path, scheme=scheme)
    site.force_login = False
    page = site.pages["Template:DreamFactory Releases"]
    page.save(content, summary="Update GitHub releases (automated)")
    print("  Updated Template:DreamFactory Releases")
    return True


def main():
    parser = argparse.ArgumentParser(description="Fetch GitHub releases for the wiki")
    parser.add_argument("--wiki-url", default=f"http://{DEFAULT_WIKI}",
                        help="MediaWiki URL")
    parser.add_argument("--count", type=int, default=5,
                        help="Number of releases to fetch")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print output without uploading")
    args = parser.parse_args()

    # Parse URL
    url = args.wiki_url.replace("https://", "").replace("http://", "")
    host = url.split("/")[0]
    path = "/" + "/".join(url.split("/")[1:]) if "/" in url else "/"
    if not path.endswith("/"):
        path += "/"
    scheme = "https" if args.wiki_url.startswith("https://") else "http"

    print(f"Fetching {args.count} releases from GitHub...")
    releases = fetch_releases(args.count)
    print(f"  Found {len(releases)} releases")
    for r in releases:
        print(f"    {r['version']} ({r['date']})")

    content = format_releases(releases)
    upload_releases(host, path, scheme, content, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    exit(main())
