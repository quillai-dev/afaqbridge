#!/bin/bash
# Browser E2E: starts the dev stack + SIMULATED DocuSeal, prepares fixtures, runs Chromium, prints the server-side report.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"; cd "$DIR"
pkill -f '[d]ocuseal_sim.py' 2>/dev/null; sleep 1
rm -f artifacts/*.png artifacts/result.json; rm -rf /tmp/e2e; mkdir -p /tmp/e2e; chmod 777 /tmp/e2e
/home/claude/application-office/scripts/start-dev-stack.sh || exit 1
RUN='(cd /home/frappe/frappe-bench && su frappe -c "env/bin/python /home/claude/application-office/scripts/frappe_run.py office.localhost /home/claude/application-office/tests/e2e/e2e_harness.py'
eval "$RUN setup\")"
export DS_TOKEN=$(python3 -c "import json;print(json.load(open('/tmp/e2e/state.json'))['ds_token'])") DS_SECRET=$(python3 -c "import json;print(json.load(open('/tmp/e2e/state.json'))['ds_secret'])") FRAPPE_URL=http://office.localhost:8000 DS_PORT=9100
(setsid nohup /home/frappe/frappe-bench/env/bin/python docuseal_sim.py > /tmp/docuseal_sim.out 2>&1 < /dev/null &) ; sleep 2
(cd "$DIR" && node e2e.mjs); RC=$?
eval "$RUN flush\")" >/dev/null 2>&1; eval "$RUN report\")" | grep REPORT | sed 's/^REPORT //' > artifacts/server-report.json
echo "--- DocuSeal simulator log:"; cat /tmp/docuseal_sim.log 2>/dev/null | sort | uniq -c | head
exit $RC
