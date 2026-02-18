#!/bin/bash
# generate_sitemap.sh - Generate sitemap.xml for the DreamFactory wiki
#
# Runs MediaWiki's built-in sitemap generator inside the Docker container.
# Output is written to the web root so nginx can serve it at /sitemap.xml.
#
# Usage:
#   ./generate_sitemap.sh                    # staging (default)
#   ./generate_sitemap.sh production         # production

set -euo pipefail

ENV="${1:-staging}"

if [ "$ENV" = "production" ]; then
    CONTAINER="wiki-app"
    SERVER="https://wiki.dreamfactory.com"
else
    CONTAINER="staging-wiki-app"
    SERVER="http://localhost:8082"
fi

echo "Generating sitemap for $ENV ($SERVER)..."

docker exec "$CONTAINER" php maintenance/generateSitemap.php \
    --fspath=/var/www/html/ \
    --server="$SERVER" \
    --urlpath=/ \
    --compress=no

echo "Sitemap generated successfully."
echo "Verify: curl -s ${SERVER}/sitemap.xml | head"
