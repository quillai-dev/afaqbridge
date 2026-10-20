#!/bin/bash
# Encrypted backup of the PRODUCTION site (docker compose). NOT executed in the build sandbox - verify on your host
# (run a restore into a scratch site, see docs/backup-restore.md) before relying on it.
set -euo pipefail
set -a; . ./.env; set +a
: "${BACKUP_PASSPHRASE_FILE:?}"; OUT=${BACKUP_DIR:-./backups}; mkdir -p "$OUT"; chmod 700 "$OUT"
FD=upstream/frappe_docker
C="docker compose --env-file .env -f $FD/compose.yaml -f $FD/overrides/compose.mariadb.yaml -f $FD/overrides/compose.redis.yaml -f $FD/overrides/compose.https.yaml -f compose.yaml"
$C exec -T backend bench --site "$SITE_NAME" backup --with-files >/dev/null
STAMP=$(date +%Y%m%d-%H%M%S)
$C exec -T backend bash -c "cd sites/$SITE_NAME/private/backups && tar -cf - \$(ls -t | head -4)" \
 | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass file:"$BACKUP_PASSPHRASE_FILE" -out "$OUT/$SITE_NAME-$STAMP.tar.enc"
sha256sum "$OUT/$SITE_NAME-$STAMP.tar.enc" > "$OUT/$SITE_NAME-$STAMP.tar.enc.sha256"; chmod 600 "$OUT"/*
# DocuSeal data is separate: dump its database too
$C exec -T docuseal-db pg_dump -U docuseal docuseal | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass file:"$BACKUP_PASSPHRASE_FILE" -out "$OUT/docuseal-$STAMP.sql.enc"
echo "backups written to $OUT (also copy off-host)"
