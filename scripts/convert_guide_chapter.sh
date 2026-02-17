#!/bin/bash
#
# convert_guide_chapter.sh - Convert a single Hugo guide chapter to MediaWiki
#
# Usage:
#   ./convert_guide_chapter.sh <guide_chapter_path> <output_wiki_name>
#
# Example:
#   ./convert_guide_chapter.sh \
#     "../guide/dreamfactory-book-v2/content/en/docs/Integrating Salesforce Data/_index.md" \
#     "Integrating_Salesforce_Data"
#
# The script:
#   1. Runs pandoc -f markdown -t mediawiki
#   2. Runs postprocess.py on the output
#   3. Saves to converted/<output_wiki_name>.wiki
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/converted"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <guide_chapter_path> <output_wiki_name>"
    echo ""
    echo "Example:"
    echo "  $0 '../guide/.../Integrating Salesforce Data/_index.md' 'Integrating_Salesforce_Data'"
    exit 1
fi

GUIDE_PATH="$1"
WIKI_NAME="$2"

if [[ ! -f "$GUIDE_PATH" ]]; then
    echo -e "${RED}Error: Source file not found: $GUIDE_PATH${NC}"
    exit 1
fi

# Check for required tools
if ! command -v pandoc &> /dev/null; then
    echo -e "${RED}Error: pandoc is not installed${NC}"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

OUTPUT_FILE="$OUTPUT_DIR/${WIKI_NAME}.wiki"

echo -n "Converting: $(basename "$GUIDE_PATH") -> ${WIKI_NAME}.wiki ... "

# Step 1: Convert with pandoc
if pandoc -f markdown -t mediawiki "$GUIDE_PATH" -o "$OUTPUT_FILE" 2>/dev/null; then
    # Step 2: Run post-processor with source path for frontmatter/categories
    if python3 "$SCRIPT_DIR/postprocess.py" "$OUTPUT_FILE" "$GUIDE_PATH" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${GREEN}OK${NC} (post-process warning)"
    fi
else
    echo -e "${RED}FAILED${NC}"
    exit 1
fi

echo "  Output: $OUTPUT_FILE"
