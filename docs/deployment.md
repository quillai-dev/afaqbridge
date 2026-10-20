# Deployment

> **Status:** the container deployment below is **unverified** - the build sandbox had no Docker. Everything here follows the
> pinned `frappe_docker` (`df2a3b72`) layout and passes static YAML checks only. Treat the first deploy as a rehearsal on a
> disposable host, run `make test` against a throw-away site, and fix what breaks. The *native* dev procedure (section 2) is the one that was executed.

## 1. Container deployment (Docker Compose)
Prerequisites: Linux host with Docker ≥ 24 + Compose v2, DNS names for the site and DocuSeal, ports 80/443, an off-host backup target.
```
git clone <this repo> && cd application-office
git clone --depth 1 --branch main https://github.com/frappe/frappe_docker upstream/frappe_docker   # then check out the pinned commit df2a3b72
git -C upstream/frappe_docker checkout df2a3b72910634cf0e878b59eccf68a93736bf9d
# push apps/application_office to a Git remote and put its URL in deploy/apps.json  (the image build clones it)
make setup            # creates .env (mode 600) with random secrets; edit domains / tags
make image            # builds frappe v16.52.0 + erpnext v16.51.1 + application_office into CUSTOM_IMAGE:CUSTOM_TAG
make up               # mariadb, redis, backend, workers, scheduler, proxy(HTTPS), create-site, docuseal
make status
```
First run: `create-site` runs `bench new-site … --install-app erpnext --install-app application_office`. Then log in as
`Administrator` with `ADMIN_PASSWORD` from `.env`, complete the ERPNext Setup Wizard (company, country, **currency, chart of accounts, tax** - nothing is assumed by this platform), then:
1. Create the outgoing **Email Account** (required - without it every notification logs `Error`).
2. `AO Settings`: office name, **reviewed** disclaimer, terms/privacy URLs, retention, DocuSeal (optional).
3. Create staff users with AO roles; each staff member enrols 2FA at first login (enabled per role).
4. Create your `AO Program` records and **publish** them (requires a verification date).

Environment variables: see `.env.example` (every variable commented). Secrets never go in Git (`.gitignore` covers `.env`, backups, `upstream/`).
Databases and Redis have no published ports; only the proxy listens on 80/443. Resource limits are set in `compose.yaml` for backend, DocuSeal and its DB - tune after measuring.

## 2. Native development stack (what was actually run)
```
make dev-up        # MariaDB, Redis x2, SMTP sink, web server on :8000
make dev-site      # recreate site: ERPNext + application_office + sample company   (~4 min on 1 CPU)
make dev-test      # 61 tests
make dev-http-test # 14 HTTP tests
```
Dev credentials (`admin-dev-only`, `devroot-only-local`) are for a throw-away sandbox only. Requires Python 3.14, Node 24, MariaDB, Redis, `bench` as a **non-root** user.

## 3. Upgrades (safe procedure)
1. Read upstream release notes for Frappe/ERPNext/DocuSeal; never jump majors without a staging rehearsal.
2. `make backup` and **test-restore it into a scratch site**.
3. Bump the pinned tags (`.env`, `deploy/apps.json`, `scripts/pin-report.sh` table, docs), rebuild the image with a **new tag**.
4. Deploy to staging from the restored backup; run `make test` and the HTTP suite; click through one case.
5. Production: maintenance mode on → `make up` with the new tag (bench migrate runs via the upstream migrator override: add `compose.migrator.yaml`) → verify → maintenance off.
6. Rollback = previous image tag + restore the pre-upgrade backup (migrations are not reversible).
DocuSeal: upgrade independently (pinned tag), then re-test webhook + signing.
