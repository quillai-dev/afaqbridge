#!/bin/sh
# AfaqBridge public edge (nginx). Renders the config from templates + environment, then runs nginx in the
# foreground. Contains no secrets: only host names and tunables are substituted.
set -eu
TPL=/opt/afaqbridge/templates
OUT=/etc/nginx/conf.d/afaqbridge.conf
: "${EDGE_MODE:=dev}" "${SITE_NAME:?SITE_NAME not set}" "${DOCUSEAL_HOST:?DOCUSEAL_HOST not set}"
: "${TLS_CERT_NAME:=afaqbridge}" "${EDGE_READ_TIMEOUT:=300}" "${EDGE_WS_TIMEOUT:=3600}"
: "${EDGE_CLIENT_MAX_BODY_SIZE:=50m}" "${EDGE_DOCUSEAL_MAX_BODY_SIZE:=100m}" "${EDGE_LOGIN_RATE:=30r/m}"
: "${FRONTEND_UPSTREAM:=frontend:8080}" "${DOCUSEAL_UPSTREAM:=docuseal:3000}"
export EDGE_MODE SITE_NAME DOCUSEAL_HOST TLS_CERT_NAME EDGE_READ_TIMEOUT EDGE_WS_TIMEOUT \
       EDGE_CLIENT_MAX_BODY_SIZE EDGE_DOCUSEAL_MAX_BODY_SIZE EDGE_LOGIN_RATE FRONTEND_UPSTREAM DOCUSEAL_UPSTREAM

VARS='${SITE_NAME} ${DOCUSEAL_HOST} ${TLS_CERT_NAME} ${EDGE_READ_TIMEOUT} ${EDGE_WS_TIMEOUT} ${EDGE_CLIENT_MAX_BODY_SIZE} ${EDGE_DOCUSEAL_MAX_BODY_SIZE} ${EDGE_LOGIN_RATE} ${FRONTEND_UPSTREAM} ${DOCUSEAL_UPSTREAM}'
CERT_DIR=/etc/letsencrypt/live/$TLS_CERT_NAME

render() {
  rm -f /etc/nginx/conf.d/default.conf
  case "$EDGE_MODE" in
    dev)  t=dev ;;
    prod) if [ -s "$CERT_DIR/fullchain.pem" ] && [ -s "$CERT_DIR/privkey.pem" ]; then t=prod; else
            echo "edge: no certificate in $CERT_DIR yet - serving HTTP-01 challenge only (run: make tls-issue)"; t=bootstrap; fi ;;
    *) echo "edge: EDGE_MODE must be dev or prod" >&2; exit 1 ;;
  esac
  mkdir -p /etc/nginx/afaqbridge
  for f in "$TPL"/*.inc; do envsubst "$VARS" < "$f" > "/etc/nginx/afaqbridge/$(basename "$f")"; done
  envsubst "$VARS" < "$TPL/$t.conf.template" > "$OUT.new"
  mv "$OUT.new" "$OUT"
  echo "edge: rendered '$t' configuration for $SITE_NAME / $DOCUSEAL_HOST"
}

render
nginx -t
# pick up renewed certificates (or a freshly issued one) without a restart
( while :; do sleep 6h; render && nginx -t && nginx -s reload; done ) &
exec nginx -g 'daemon off;'
