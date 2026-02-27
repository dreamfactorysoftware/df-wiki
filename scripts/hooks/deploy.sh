#!/bin/bash
set -euo pipefail

echo "=== Deploy triggered at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

echo "Pulling latest from main..."
git pull --ff-only origin main

echo "Testing nginx config..."
docker exec "$NGINX_CONTAINER" nginx -t

echo "Reloading nginx..."
docker exec "$NGINX_CONTAINER" nginx -s reload

echo "Regenerating sitemap..."
docker exec "$APP_CONTAINER" php maintenance/generateSitemap.php \
  --fspath=/var/www/html/ --server="$WIKI_SERVER" --urlpath=/ --compress=no

echo "=== Deploy complete ==="
