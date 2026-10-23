# Browser E2E

Run: `tests/e2e/run-e2e.sh` (takes ~5 min on 1 CPU - run it detached and poll: `nohup tests/e2e/run-e2e.sh > /tmp/e2e.log 2>&1 &`).

Prerequisites (dev sandbox only; paths are specific to the build sandbox - adapt them):
- the dev stack: `make dev-up` (MariaDB, Redis, web server :8000, background worker, Socket.IO, SMTP sink on :1025)
- a Chromium via npm: `mkdir -p /opt/browser && cd /opt/browser && npm init -y && npm install puppeteer-core @sparticuz/chromium`,
  then `ln -s /opt/browser/node_modules tests/e2e/node_modules` (the symlink is git-ignored)
- DocuSeal is **simulated** by `docuseal_sim.py` (started by the runner). It is not the real product.

Outputs: `artifacts/*.png` (screenshots, synthetic test data only), `artifacts/result.json`, `artifacts/server-report.json`.
See docs/implementation-plan.md for what the run covers and its limitations.
