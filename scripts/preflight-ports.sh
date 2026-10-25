#!/bin/bash
# Refuse to start when a host port we would publish is already taken by something else (e.g. another project
# already using 80/443). Never stops, kills or reconfigures anything - it only reports.
set -uo pipefail
MODE=${1:-dev}
ENVF=${ENV_FILE:-.env}
get() { grep -E "^$1=" "$ENVF" 2>/dev/null | tail -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//'; }
PROJECT=$(get COMPOSE_PROJECT_NAME); PROJECT=${PROJECT:-application-office}
if [ "$MODE" = prod ]; then PORTS="$(get EDGE_PROD_HTTP_PORT) $(get EDGE_PROD_HTTPS_PORT)"; PORTS=${PORTS:- 80 443}; [ -n "$(get EDGE_PROD_HTTP_PORT)" ] || PORTS="80 $(get EDGE_PROD_HTTPS_PORT)"; else PORTS=$(get EDGE_HTTP_PORT); PORTS=${PORTS:-8088}; fi
rc=0
for p in $PORTS; do
  [ -n "$p" ] || continue
  if ss -H -ltn "sport = :$p" 2>/dev/null | grep -q .; then
    # ours already (re-running `make up`)? then it is fine.
    if command -v docker >/dev/null && docker ps -q --filter "label=com.docker.compose.project=$PROJECT" --filter "publish=$p" | grep -q .; then
      echo "port $p: already published by this project ($PROJECT) - ok"; continue; fi
    echo "port $p: IN USE by another process on this host:" >&2
    ss -ltnp "sport = :$p" 2>/dev/null | tail -n +2 >&2
    echo "  -> nothing was changed. Choose another EDGE_HTTP_PORT / EDGE_HTTPS_PORT (or EDGE_BIND_ADDR) in .env." >&2
    rc=1
  else
    echo "port $p: free"
  fi
done
exit $rc
