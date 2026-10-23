#!/bin/bash
# Docker-host deployment rehearsal. RUN THIS ON A DISPOSABLE DOCKER HOST (NOT the build sandbox - it has no Docker).
# It performs the steps in docs/rehearsal-docker.md and writes an evidence log to ./rehearsal-evidence-<timestamp>.log.
# Every step prints PASS/FAIL; nothing is assumed. Exit code 1 if any step fails.
set -u
LOG="rehearsal-evidence-$(date +%Y%m%d-%H%M%S).log"; FAILS=0
step(){ local n="$1"; shift; echo "=== $n" | tee -a "$LOG"; if "$@" >>"$LOG" 2>&1; then echo "PASS $n" | tee -a "$LOG"; else echo "FAIL $n" | tee -a "$LOG"; FAILS=$((FAILS+1)); fi; }
need(){ command -v "$1" >/dev/null; }
step "docker + compose present"           bash -c 'docker version && docker compose version'
step ".env exists (run: make setup)"       test -f .env
[ "$FAILS" -eq 0 ] || { echo "---- prerequisites missing ($FAILS); aborting - nothing was rehearsed. Evidence: $LOG" | tee -a "$LOG"; exit 1; }
step "merged compose config renders"       bash -c 'make -s need-docker && docker compose --env-file .env -f upstream/frappe_docker/compose.yaml -f upstream/frappe_docker/overrides/compose.mariadb.yaml -f upstream/frappe_docker/overrides/compose.redis.yaml -f upstream/frappe_docker/overrides/compose.https.yaml -f compose.yaml config -q'
step "custom image builds (make image)"    make image
step "stack starts healthy (make up)"      make up
step "all services running/healthy"       bash -c 'out=$(make -s status) && [ -n "$out" ] && echo "$out" && ! echo "$out" | grep -Ei "unhealthy|exited \([1-9]|restarting"'
. ./.env 2>/dev/null
step "site answers /api/method/ping over HTTPS" bash -c "curl -fsS --resolve ${SITE_NAME}:443:127.0.0.1 -k https://${SITE_NAME}/api/method/ping"
step "portal page served"                  bash -c "curl -fsS --resolve ${SITE_NAME}:443:127.0.0.1 -k https://${SITE_NAME}/office-portal | grep -q ao-app"
step "HTTP redirects to HTTPS"             bash -c "curl -sI --resolve ${SITE_NAME}:80:127.0.0.1 http://${SITE_NAME}/ | grep -Ei '^location: https://'"
step "Secure+HttpOnly cookie flags over TLS" bash -c "curl -sik --resolve ${SITE_NAME}:443:127.0.0.1 https://${SITE_NAME}/api/method/login -d usr=x -d pwd=y | grep -i '^set-cookie' | grep -i secure"
step "DB/Redis not reachable from host"    bash -c '! (echo > /dev/tcp/127.0.0.1/3306) 2>/dev/null && ! (echo > /dev/tcp/127.0.0.1/6379) 2>/dev/null'
step "app tests inside container (TEST_SITE, disposable site!)" make test TEST_SITE="${TEST_SITE:-}"
step "encrypted backup (make backup)"      make backup
echo "---- $FAILS step(s) failed; evidence in $LOG" | tee -a "$LOG"; exit $((FAILS>0))
