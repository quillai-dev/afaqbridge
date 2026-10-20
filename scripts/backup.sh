#!/bin/bash
# Encrypted backup of the DEV bench site (database + public/private files + site config).
# Usage: BACKUP_PASSPHRASE_FILE=/path/to/file ./backup.sh [site]
# The passphrase file must live OUTSIDE the repository and outside the backup directory.
set -euo pipefail
SITE=${1:-office.localhost}
OUT=${BACKUP_DIR:-/home/frappe/ao-backups}
: "${BACKUP_PASSPHRASE_FILE:?set BACKUP_PASSPHRASE_FILE to a file containing the encryption passphrase}"
[ -s "$BACKUP_PASSPHRASE_FILE" ] || { echo "passphrase file empty/missing" >&2; exit 1; }
export PATH=/opt/node24/node_modules/.bin:/home/frappe/benchenv/bin:/usr/local/bin:$PATH
BENCH=${BENCH:-/home/frappe/frappe-bench}
cd "$BENCH"
mkdir -p "$OUT"; chmod 700 "$OUT"
bench --site "$SITE" backup --with-files >/tmp/ao-backup.log 2>&1 || { cat /tmp/ao-backup.log; exit 1; }
D="$BENCH/sites/$SITE/private/backups"
STAMP=$(date +%Y%m%d-%H%M%S)
LATEST=$(ls -t "$D"/*-database.sql.gz | head -1); PREFIX=${LATEST%-database.sql.gz}
tar -C "$D" -cf - "$(basename "$PREFIX")-database.sql.gz" "$(basename "$PREFIX")-files.tar" "$(basename "$PREFIX")-private-files.tar" "$(basename "$PREFIX")-site_config_backup.json" \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass file:"$BACKUP_PASSPHRASE_FILE" -out "$OUT/$SITE-$STAMP.tar.enc"
sha256sum "$OUT/$SITE-$STAMP.tar.enc" > "$OUT/$SITE-$STAMP.tar.enc.sha256"
chmod 600 "$OUT"/$SITE-$STAMP.*
# plaintext working copies are removed immediately
rm -f "$PREFIX"-database.sql.gz "$PREFIX"-files.tar "$PREFIX"-private-files.tar "$PREFIX"-site_config_backup.json
echo "$OUT/$SITE-$STAMP.tar.enc"
