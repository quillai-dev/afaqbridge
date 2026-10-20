#!/bin/bash
# Create (or recreate) the DEVELOPMENT site: ERPNext + application_office + company bootstrap.
# Runs as the unprivileged `frappe` user from the dev bench. Dev credentials only - never reuse in production.
set -euo pipefail
SITE=${1:-office.localhost}
BENCH=/home/frappe/frappe-bench
export PATH=/opt/node24/node_modules/.bin:/home/frappe/benchenv/bin:/usr/local/bin:/home/frappe/.local/bin:$PATH
cd $BENCH
mariadb -uroot -pdevroot-only-local -e "select 1" >/dev/null
bench drop-site $SITE --force --db-root-password devroot-only-local --no-backup 2>/dev/null || true
bench new-site $SITE --db-root-password devroot-only-local --admin-password admin-dev-only --install-app erpnext --no-mariadb-socket
RUN="/home/frappe/frappe-bench/env/bin/python /home/claude/application-office/scripts/frappe_run.py $SITE"
BOOT=/home/claude/application-office/scripts/dev_bootstrap.py
$RUN $BOOT company
bench --site $SITE install-app application_office
$RUN $BOOT finish
bench --site $SITE set-config allow_tests true
echo "site $SITE ready"
