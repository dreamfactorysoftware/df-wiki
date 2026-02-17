#!/bin/bash
#
# batch_convert.sh - Batch convert markdown files to MediaWiki format
#
# Usage:
#   ./batch_convert.sh [source_dir] [output_dir]
#
# Converts all markdown files in source_dir to MediaWiki format,
# placing outputs in output_dir with .wiki extension.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# Default paths
SOURCE_DIR="${1:-$BASE_DIR/df-docs/df-docs/docs}"
OUTPUT_DIR="${2:-$SCRIPT_DIR/converted}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================"
echo "DreamFactory Documentation Batch Converter"
echo "============================================"
echo ""
echo "Source directory: $SOURCE_DIR"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Check for required tools
if ! command -v pandoc &> /dev/null; then
    echo -e "${RED}Error: pandoc is not installed${NC}"
    echo "Install with: apt-get install pandoc"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed${NC}"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Count files
TOTAL_FILES=$(find "$SOURCE_DIR" -name "*.md" -type f | wc -l)
CONVERTED=0
FAILED=0

echo "Found $TOTAL_FILES markdown files to convert"
echo ""

# Build skip list from migration_inventory.csv (Skip-EmptyDraft entries)
INVENTORY="$SCRIPT_DIR/migration_inventory.csv"
SKIPPED=0
declare -A SKIP_FILES
if [[ -f "$INVENTORY" ]]; then
    # Use python to extract skip entries (handles CSV quoting correctly)
    while read -r skip_basename; do
        SKIP_FILES["$skip_basename"]=1
    done < <(python3 -c "
import csv, sys
from pathlib import Path
with open('$INVENTORY', 'r') as f:
    for row in csv.DictReader(f):
        if row.get('status','') == 'Skip-EmptyDraft':
            print(Path(row.get('source_path','')).name)
")
    echo "Loaded ${#SKIP_FILES[@]} Skip-EmptyDraft entries from inventory"
    echo ""
fi

# Process each markdown file
# Use process substitution to avoid pipe subshell (preserves counter variables)
while read -r md_file; do
    # Skip hidden files and _ai-reference.md (too large)
    filename=$(basename "$md_file")
    if [[ "$filename" == .* ]] || [[ "$filename" == "_ai-reference.md" ]]; then
        continue
    fi

    # Skip files marked as Skip-EmptyDraft in inventory
    if [[ -n "${SKIP_FILES[$filename]+x}" ]]; then
        echo -e "Skipping: ${md_file#$SOURCE_DIR/} ${YELLOW}(Skip-EmptyDraft)${NC}"
        ((SKIPPED++)) || true
        continue
    fi

    # Create relative path structure in output
    rel_path="${md_file#$SOURCE_DIR/}"
    output_path="$OUTPUT_DIR/${rel_path%.md}.wiki"
    output_dir=$(dirname "$output_path")

    mkdir -p "$output_dir"

    echo -n "Converting: $rel_path ... "

    # Convert with pandoc
    if pandoc -f markdown -t mediawiki "$md_file" -o "$output_path" 2>/dev/null; then
        # Run post-processor
        if python3 "$SCRIPT_DIR/postprocess.py" "$output_path" "$md_file" 2>/dev/null; then
            echo -e "${GREEN}OK${NC}"
            ((CONVERTED++)) || true
        else
            echo -e "${YELLOW}OK (post-process warning)${NC}"
            ((CONVERTED++)) || true
        fi
    else
        echo -e "${RED}FAILED${NC}"
        ((FAILED++)) || true
    fi
done < <(find "$SOURCE_DIR" -name "*.md" -type f)

echo ""
echo "============================================"
echo "Conversion complete!"
echo "  Converted: $CONVERTED"
echo "  Skipped:   $SKIPPED (Skip-EmptyDraft)"
echo "  Failed:    $FAILED"
echo "  Output:    $OUTPUT_DIR"
echo "============================================"
