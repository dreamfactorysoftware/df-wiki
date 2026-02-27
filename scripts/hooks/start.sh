#!/bin/sh
# Expand env vars in hooks config, then start webhook
sed -e "s|\${WEBHOOK_TOKEN}|${WEBHOOK_TOKEN}|g" \
    -e "s|\${NGINX_CONTAINER}|${NGINX_CONTAINER}|g" \
    -e "s|\${APP_CONTAINER}|${APP_CONTAINER}|g" \
    -e "s|\${WIKI_SERVER}|${WIKI_SERVER}|g" \
    /etc/webhook/hooks.json > /tmp/hooks.json
exec webhook -hooks /tmp/hooks.json -verbose
