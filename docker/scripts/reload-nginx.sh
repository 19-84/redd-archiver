#!/bin/sh
# ABOUTME: Simple nginx reload script called after certbot certificate renewal
# ABOUTME: Finds the nginx container dynamically and sends reload signal for zero-downtime renewal

set -e

echo "[$(date)] Certificate renewal detected, reloading nginx..."

# Find nginx container dynamically
NGINX_CONTAINER=$(docker ps --filter "name=nginx" --format "{{.Names}}" | head -n1)

if [ -z "$NGINX_CONTAINER" ]; then
    echo "[$(date)] ERROR: Nginx container not found" >&2
    exit 1
fi

# Send reload signal to nginx (zero-downtime reload)
docker exec "$NGINX_CONTAINER" nginx -s reload

if [ $? -eq 0 ]; then
    echo "[$(date)] Nginx reloaded successfully"
else
    echo "[$(date)] ERROR: Nginx reload failed" >&2
    exit 1
fi
