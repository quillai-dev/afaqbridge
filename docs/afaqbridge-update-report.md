# AfaqBridge update - acceptance report (evidence, not claims)

Environment: build sandbox, **no Docker daemon**. Native Frappe v16.52.0 + ERPNext v16.51.1 + this app on MariaDB 10.11, Redis, real nginx 1.28.0 (built from source), headless Chromium 153.

| # | Required check | Result |
|---|---|---|
| 1 | Validate final Compose | ✅ `docker compose config` (real v2.40.3) OK for MODE=dev and MODE=prod; dev publishes only 127.0.0.1:8088, prod 80/443, no Traefik |
| 2 | Build changed images, start services | ⛔ **not done** (no Docker). Images unchanged except config; `edge` uses `nginx:1.28.0-alpine`, `certbot/certbot:v4.0.0` (tags not verified against a registry) |
| 3 | Site loads through the public entry point | ✅ via edge → upstream-frontend nginx template → Frappe at `http://afaqbridge.localhost:8088` (sandbox emulation of the chain, without containers) |
| 4 | Login, session, static assets, WebSocket | ✅ login + desk (Administrator), assets 200 with correct MIME, socket.io `transport=websocket connected=true` through edge+frontend (needs the `SITE_NAME` network alias on edge - emulated with /etc/hosts) |
| 5 | Arabic default for fresh visitor, RTL on main flows | ✅ English-language browser → `lang=ar dir=rtl` on login, portal, desk. Not covered: every desk page (5 scanned), forms beyond Case/Settings/Program, print formats |
| 6 | Switch AR/EN (login + authenticated) | ✅ login picker, portal switch (same URL, unsaved-input confirmation), desk switch (same page) |
| 7 | English stays LTR and readable | ✅ `dir=ltr lang=en` on all three; persists after reload |
| 8 | DocuSeal routing/signing | 🟡 host routing to the **simulator** verified (and host separation); real DocuSeal never run; signing flow only by existing simulator tests. Arabic/RTL in DocuSeal: see docs/localization.md |
| 9 | Health, logs, status codes, routing | ✅ edge/frontend logs reviewed: only intended 429/413/444/503 and start-up 502 while backend was down; no Traceback in bench log. Container health: ⛔ n/a |
| 10 | No conflict with other host services | 🟡 dev binds only 127.0.0.1:8088; `scripts/preflight-ports.sh` refuses busy ports. Not exercised on a real multi-project Docker host |
| 11 | Existing tests + regression tests | ✅ in-app 73/73 (61 existing + 12 new localization); nginx edge 10/10; browser localization 21/21. ⛔ Not re-run: 14 HTTP tests, 23-check E2E, backup drills (they assume the old English UI / old site name) |
| 12 | Existing data intact | 🟡 migration only changes settings; no destructive command exists in the new targets. Not exercised against an existing populated volume |

Defects found by testing and fixed: relative bind paths resolved inside upstream/; prod ports inherited the dev port; duplicate `proxy_read_timeout`; duplicate/preloaded HSTS;
www module name (`office_portal.py`); missing Arabic for Frappe login strings; realtime auth hairpin (edge alias).
Test shim (NOT in repo): 2FA disabled for System Manager on the throw-away sandbox site so the browser could log in as Administrator.
`scripts/dev_bootstrap.py` still passes language "English" to the setup wizard (used only by the old English E2E); choose Arabic in real deployments.
