#!/bin/bash
# Restore an encrypted backup into a (new or existing) site of the DEV bench.
# Usage: BACKUP_PASSPHRASE_FILE=... ./restore.sh <backup.tar.enc> <target-site>
# Refuses to overwrite an existing site unless FORCE=1. Always restore into a scratch site first.
set -euo pipefail
ENC=${1:?backup file}; TARGET=${2:?target site}
: "${BACKUP_PASSPHRASE_FILE:?}"
export PATH=/opt/node24/node_modules/.bin:/home/frappe/benchenv/bin:/usr/local/bin:$PATH
BENCH=${BENCH:-/home/frappe/frappe-bench}; cd "$BENCH"
if [ -d "sites/$TARGET" ] && [ "${FORCE:-0}" != 1 ]; then echo "site $TARGET exists; set FORCE=1 to overwrite" >&2; exit 1; fi
[ -f "$ENC.sha256" ] && sha256sum -c "$ENC.sha256" >/dev/null || { echo "checksum missing/mismatch" >&2; exit 1; }
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT; chmod 700 "$W"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass file:"$BACKUP_PASSPHRASE_FILE" -in "$ENC" | tar -C "$W" -xf -
DB=$(ls "$W"/*-database.sql.gz); PUB=$(ls "$W"/*-files.tar | grep -v private); PRIV=$(ls "$W"/*-private-files.tar)
[ -d "sites/$TARGET" ] || bench new-site "$TARGET" --db-root-password "${DB_ROOT_PASSWORD:?}" --admin-password "$(openssl rand -hex 12)" --no-mariadb-socket
bench --site "$TARGET" --force restore "$DB" --with-public-files "$PUB" --with-private-files "$PRIV" --db-root-password "${DB_ROOT_PASSWORD:?}"
bench --site "$TARGET" migrate
echo "restored into $TARGET"
