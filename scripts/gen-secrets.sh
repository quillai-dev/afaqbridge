#!/bin/bash
# Fill empty secret variables in .env with random values. Never overwrites a value that is already set.
set -euo pipefail
F=${1:-.env}; [ -f "$F" ] || { echo "$F not found" >&2; exit 1; }
for k in DB_PASSWORD ADMIN_PASSWORD DOCUSEAL_DB_PASSWORD; do
  grep -qE "^$k=.+" "$F" || sed -i "s|^$k=.*|$k=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-28)|" "$F"; done
grep -qE "^DOCUSEAL_SECRET_KEY_BASE=.+" "$F" || sed -i "s|^DOCUSEAL_SECRET_KEY_BASE=.*|DOCUSEAL_SECRET_KEY_BASE=$(openssl rand -hex 64)|" "$F"
chmod 600 "$F"; echo "secrets filled in $F (mode 600)"
