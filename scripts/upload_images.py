#!/usr/bin/env python3
"""Upload available guide images to the staging MediaWiki wiki."""

import os
import sys
import re
import glob
import mimetypes

import mwclient

IMAGES_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'guide', 'dreamfactory-book-v2',
    'themes', 'docsy', 'static', 'images'
)
CONVERTED_DIR = os.path.join(os.path.dirname(__file__), 'converted')
WIKI_HOST = 'localhost:8082'
WIKI_PATH = '/'
WIKI_SCHEME = 'http'


def find_all_images(images_dir):
    """Build a dict mapping bare filename -> full path for all images."""
    result = {}
    for root, dirs, files in os.walk(images_dir):
        for f in files:
            full_path = os.path.join(root, f)
            # Store by bare filename (lowercase for case-insensitive matching)
            result[f.lower()] = full_path
    return result


def find_referenced_images(converted_dir):
    """Extract all unique [[File:...]] references from .wiki files."""
    pattern = re.compile(r'\[\[File:([^]|]+)')
    refs = set()
    for wiki_file in glob.glob(os.path.join(converted_dir, '**', '*.wiki'), recursive=True):
        with open(wiki_file, 'r') as fh:
            for match in pattern.finditer(fh.read()):
                refs.add(match.group(1))
    return refs


def main():
    images_dir = os.path.normpath(IMAGES_DIR)
    converted_dir = os.path.normpath(CONVERTED_DIR)

    print(f"Scanning images in: {images_dir}")
    available = find_all_images(images_dir)
    print(f"  Found {len(available)} image files")

    print(f"Scanning wiki references in: {converted_dir}")
    referenced = find_referenced_images(converted_dir)
    print(f"  Found {len(referenced)} unique image references")

    # Match referenced images to available files
    to_upload = {}  # wiki_filename -> local_path
    missing = []
    for ref in sorted(referenced):
        key = ref.lower()
        if key in available:
            to_upload[ref] = available[key]
        else:
            missing.append(ref)

    print(f"\nMatched: {len(to_upload)}")
    print(f"Missing: {len(missing)}")

    if missing:
        print("\nMissing images (no file in repo):")
        for m in sorted(missing):
            print(f"  - {m}")

    if not to_upload:
        print("\nNothing to upload.")
        return

    # Connect to wiki
    print(f"\nConnecting to wiki at {WIKI_HOST}...")
    site = mwclient.Site(WIKI_HOST, path=WIKI_PATH, scheme=WIKI_SCHEME)
    site.login('MigrationBot', 'BotPass12345')
    print("  Logged in as MigrationBot")

    uploaded = 0
    skipped = 0
    errors = 0

    for wiki_name, local_path in sorted(to_upload.items()):
        # MediaWiki normalizes filenames: first letter uppercase
        # The wiki_name from [[File:X]] is what we upload as
        mime_type, _ = mimetypes.guess_type(local_path)
        if not mime_type:
            mime_type = 'application/octet-stream'

        try:
            file_size = os.path.getsize(local_path)
            print(f"  Uploading {wiki_name} ({file_size:,} bytes)...", end=' ')

            with open(local_path, 'rb') as fh:
                result = site.upload(
                    fh,
                    filename=wiki_name,
                    description=f'DreamFactory guide image: {wiki_name}',
                    ignore=True  # overwrite if exists
                )

            if result.get('result') == 'Success':
                uploaded += 1
                print("OK")
            elif result.get('result') == 'Warning':
                # Warnings like "duplicate" still succeed
                uploaded += 1
                warnings = result.get('warnings', {})
                print(f"OK (warnings: {list(warnings.keys())})")
            else:
                errors += 1
                print(f"UNEXPECTED: {result}")
        except Exception as e:
            errors += 1
            import traceback
            print(f"ERROR: {e}")
            traceback.print_exc()

    print(f"\nDone: {uploaded} uploaded, {skipped} skipped, {errors} errors")
    print(f"Missing images not in repo: {len(missing)}")


if __name__ == '__main__':
    main()
