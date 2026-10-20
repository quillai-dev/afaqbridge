#!/bin/bash
# See docs/backup-restore.md. Restores into a SCRATCH site first; never overwrites production silently.
set -euo pipefail
echo "Production restore is a manual, supervised procedure - follow docs/backup-restore.md (steps verified on the dev bench with scripts/restore.sh)." >&2
exit 2
