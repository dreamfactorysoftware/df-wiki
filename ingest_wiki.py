#!/usr/bin/env python3
"""
Ingest df-wiki .wiki files into semantic memory (dreamfactory_docs collection).

Chunks by MediaWiki section headings (== Section ==).
Skips redirect stubs. Uses content-hash dedup on the service side.
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

DOCS_DIR = Path(__file__).parent / "docs"
PAGE_MAP = DOCS_DIR / "page_map.json"
MEMORY_API = "http://localhost:8765"
COLLECTION = "dreamfactory_docs"
MAX_CHUNK_CHARS = 2000  # ~500 tokens, good for BGE-large


def load_page_map() -> dict:
    if PAGE_MAP.exists():
        return json.loads(PAGE_MAP.read_text())
    return {}


def is_redirect(content: str) -> bool:
    return content.strip().startswith("#REDIRECT")


def chunk_wiki(content: str, filename: str, page_title: str) -> list[dict]:
    """Split wiki content by section headings, keeping chunks under MAX_CHUNK_CHARS."""
    chunks = []

    # Split on MediaWiki headings (== Title ==, === Title ===, etc.)
    sections = re.split(r"(?m)^(={2,6}\s*.+?\s*={2,6})\s*$", content)

    current_heading = page_title
    current_text = ""

    for part in sections:
        heading_match = re.match(r"^(={2,6})\s*(.+?)\s*={2,6}$", part)
        if heading_match:
            # Flush previous section
            if current_text.strip():
                for sub in _split_large(current_text.strip(), current_heading, filename, page_title):
                    chunks.append(sub)
            current_heading = heading_match.group(2).strip()
            current_text = ""
        else:
            current_text += part

    # Flush final section
    if current_text.strip():
        for sub in _split_large(current_text.strip(), current_heading, filename, page_title):
            chunks.append(sub)

    return chunks


def _split_large(text: str, heading: str, filename: str, page_title: str) -> list[dict]:
    """If a section is too large, split by paragraphs."""
    prefix = f"[{page_title} > {heading}]\n\n" if heading != page_title else f"[{page_title}]\n\n"

    if len(prefix + text) <= MAX_CHUNK_CHARS:
        return [{"content": prefix + text, "heading": heading, "filename": filename, "page": page_title}]

    # Split by double newlines (paragraphs)
    paragraphs = re.split(r"\n{2,}", text)
    results = []
    current = prefix

    for para in paragraphs:
        if len(current) + len(para) + 2 > MAX_CHUNK_CHARS and len(current) > len(prefix):
            results.append({"content": current.strip(), "heading": heading, "filename": filename, "page": page_title})
            current = prefix + para + "\n\n"
        else:
            current += para + "\n\n"

    if current.strip() and current.strip() != prefix.strip():
        results.append({"content": current.strip(), "heading": heading, "filename": filename, "page": page_title})

    return results


def ingest(content: str, metadata: dict) -> tuple[bool, str]:
    payload = json.dumps({
        "content": content,
        "collection": COLLECTION,
        "metadata": metadata,
    }).encode()
    req = urllib.request.Request(
        f"{MEMORY_API}/ingest",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("success", False), result.get("document_id", "")
    except Exception as e:
        return False, str(e)


def main():
    page_map = load_page_map()

    # Find all .wiki files excluding redirects/
    wiki_files = sorted(
        f for f in DOCS_DIR.rglob("*.wiki")
        if "redirects" not in str(f.relative_to(DOCS_DIR))
    )

    print(f"Found {len(wiki_files)} content files")

    total_chunks = 0
    total_ingested = 0
    total_skipped = 0
    errors = []

    for wf in wiki_files:
        content = wf.read_text(errors="replace")

        if is_redirect(content):
            print(f"  SKIP (redirect): {wf.name}")
            continue

        # Resolve page title from page_map or filename
        rel = str(wf.relative_to(DOCS_DIR))
        page_title = page_map.get(rel, wf.stem.replace("_", " "))

        chunks = chunk_wiki(content, rel, page_title)
        total_chunks += len(chunks)

        for i, chunk in enumerate(chunks):
            meta = {
                "source": "df-wiki",
                "file": chunk["filename"],
                "page": chunk["page"],
                "section": chunk["heading"],
                "chunk": i,
                "type": "documentation",
            }
            ok, doc_id = ingest(chunk["content"], meta)
            if ok:
                total_ingested += 1
            else:
                errors.append(f"{chunk['filename']}:{chunk['heading']} — {doc_id}")
                total_skipped += 1

        print(f"  {rel}: {len(chunks)} chunks")

    print(f"\nDone: {total_ingested} ingested, {total_skipped} errors, {total_chunks} total chunks")
    if errors:
        print(f"\nErrors:")
        for e in errors:
            print(f"  {e}")


if __name__ == "__main__":
    main()
