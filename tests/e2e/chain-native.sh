#!/bin/bash
# Sandbox emulation of the production request chain WITHOUT Docker (used because the build sandbox has no Docker daemon):
#   browser -> :8088 (socat = Docker port publish) -> edge (deploy/edge via edge-run.sh, real nginx)
#           -> frontend (upstream frappe_docker nginx template, rendered like nginx-entrypoint.sh) -> bench serve :8000 / socketio :9000
# Needs root, NGINX_BIN, a running bench with site afaqbridge.localhost. It does NOT prove the Docker images/volumes.
set -euo pipefail
NGINX_BIN=${NGINX_BIN:-/opt/nginx128/sbin/nginx}; R=$(cd "$(dirname "$0")/../.." && pwd)
FD=$R/upstream/frappe_docker/resources/core/nginx
mkdir -p /etc/nginx/snippets /tmp/frontend/logs
cat > /etc/nginx/snippets/security_headers.conf <<'H'
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "same-origin, strict-origin-when-cross-origin" always;
H
export BACKEND=127.0.0.1:8000 SOCKETIO=127.0.0.1:9000 NGINX_LISTEN_PORT=8080 UPSTREAM_REAL_IP_ADDRESS=127.0.0.0/8 \
       UPSTREAM_REAL_IP_HEADER=X-Forwarded-For UPSTREAM_REAL_IP_RECURSIVE=off FRAPPE_SITE_NAME_HEADER='$host' PROXY_READ_TIMEOUT=120 CLIENT_MAX_BODY_SIZE=50m
VARS='${BACKEND} ${SOCKETIO} ${UPSTREAM_REAL_IP_ADDRESS} ${UPSTREAM_REAL_IP_HEADER} ${UPSTREAM_REAL_IP_RECURSIVE} ${FRAPPE_SITE_NAME_HEADER} ${PROXY_READ_TIMEOUT} ${CLIENT_MAX_BODY_SIZE} ${NGINX_LISTEN_PORT}'
{ echo "user root; worker_processes 1; pid /tmp/frontend/nginx.pid; error_log /tmp/frontend/logs/error.log info; events{} http{ include $(dirname $NGINX_BIN)/../conf/mime.types; access_log /tmp/frontend/logs/access.log;"; envsubst "$VARS" < $FD/nginx-template.conf; echo "}"; } > /tmp/frontend/nginx.conf
$NGINX_BIN -t -c /tmp/frontend/nginx.conf -p /tmp/frontend
$NGINX_BIN -c /tmp/frontend/nginx.conf -p /tmp/frontend
echo "frontend up on :8080"
