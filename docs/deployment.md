# Deployment

> **Status:** the container deployment below is **unverified** - the build sandbox had no Docker. Everything here follows the
> pinned `frappe_docker` (`df2a3b72`) layout and passes static YAML checks only. Treat the first deploy as a rehearsal on a
> disposable host, run `make test` against a throw-away site, and fix what breaks. The *native* dev procedure (section 2) is the one that was executed.

## 0. Web entry point: nginx `edge`

```
 browser ──▶ edge (nginx 1.28, the ONLY published service) ──┬─ Host = SITE_NAME     ──▶ frontend (upstream nginx: /assets, site header, /socket.io) ──▶ backend / websocket
                                                              └─ Host = DOCUSEAL_HOST ──▶ docuseal:3000
 any other Host header → connection closed (444)             mariadb / redis / docuseal-db: no published ports, ever
```
**Why this shape.** Upstream's `frontend` already *is* nginx (static assets, `X-Frappe-Site-Name`, `/socket.io` upgrade, proxy timeouts), so it is kept
unchanged and private. Traefik (upstream `compose.https.yaml`, which needs `docker.sock`) is replaced by one small nginx that adds what `frontend` cannot:
TLS, a second host name for DocuSeal (DocuSeal cannot live under a path prefix), HSTS, per-IP login throttling, and unknown-host rejection.
Trade-off accepted: Traefik's automatic ACME is replaced by a `certbot` container (HTTP-01 webroot) and two make targets; there are two nginx hops
(edge → frontend) instead of Traefik → frontend. No other proxy publishes a host port.

**Realtime needs one detail:** Frappe's socket.io service authenticates each connection by calling `Origin` (`http(s)://SITE_NAME`, no port) from *inside* the
network. `compose.yaml` therefore gives `edge` the network alias `SITE_NAME`, so that name resolves to the edge and not to the container's own loopback. (Verified in a
sandbox emulation with an `/etc/hosts` entry; the Docker alias itself is unverified.)

### Local development (no domain, no certificate)
```
cp .env.example .env && bash scripts/gen-secrets.sh .env       # defaults: SITE_NAME=afaqbridge.localhost, port 8088
make validate          # merged compose config
make up                # MODE=dev: publishes ONLY 127.0.0.1:8088; refuses to start if that port is taken
```
**Open: http://afaqbridge.localhost:8088** (`*.localhost` resolves to loopback in browsers; for curl use `--resolve afaqbridge.localhost:8088:127.0.0.1` on older versions).
DocuSeal: `http://sign.afaqbridge.localhost:8088`. First visit shows Arabic/RTL whatever the browser language is.
Ports 80/443 are never touched in dev mode, so other projects on the host are unaffected.

### Production (real domain + HTTPS)
1. DNS A/AAAA records for `SITE_NAME` (e.g. `app.example.org`) and `DOCUSEAL_HOST` (e.g. `sign.example.org`) → the host. Ports 80 and 443 must be free
   (`make preflight MODE=prod` lists any other listener and changes nothing). If another project owns 80/443, set `EDGE_BIND_ADDR` to a spare IP or put this
   edge behind that project's proxy instead - do **not** run two proxies on the same ports.
2. `.env`: `SITE_NAME`, `SITE_URL=https://<SITE_NAME>`, `DOCUSEAL_HOST`, `DOCUSEAL_FORCE_SSL=<DOCUSEAL_HOST>`, `LETSENCRYPT_EMAIL`, `TLS_CERT_NAME`.
3. `make up MODE=prod` - edge starts in *bootstrap* mode (answers only the ACME challenge, 503 otherwise).
4. `make tls-issue MODE=prod` - one certificate for both names, then edge restarts into full TLS mode. The `certbot` service renews every 12 h and edge reloads every 6 h.
   Own certificate instead: put `fullchain.pem` + `privkey.pem` into the `letsencrypt` volume under `live/<TLS_CERT_NAME>/` and restart `edge`.
5. Existing site (do NOT rename it): keep its current `SITE_NAME`; run `make apply-branding MODE=prod` (idempotent; changes only branding/language settings) and
   `bench --site <site> set-config host_name https://<SITE_NAME>`.

### Day-to-day commands
| | |
|---|---|
| validate | `make validate [MODE=prod]` |
| start / stop | `make up [MODE=prod]` / `make down` (stops containers, **keeps volumes**) |
| inspect | `make status`, `make logs`, `docker compose ... logs edge`, `docker compose ... exec edge nginx -t` |
| certificate | `make tls-issue MODE=prod` |
| Arabic/branding on an existing site | `make apply-branding` |

## 1. Container deployment (Docker Compose)
Prerequisites: Linux host with Docker ≥ 24 + Compose v2, DNS names for the site and DocuSeal, ports 80/443 free **only for MODE=prod**, an off-host backup target.
```
git clone <this repo> && cd application-office
git clone --depth 1 --branch main https://github.com/frappe/frappe_docker upstream/frappe_docker   # then check out the pinned commit df2a3b72
git -C upstream/frappe_docker checkout df2a3b72910634cf0e878b59eccf68a93736bf9d
# push apps/application_office to a Git remote and put its URL in deploy/apps.json  (the image build clones it)
make setup            # creates .env (mode 600) with random secrets; edit domains / tags
make image            # builds frappe v16.52.0 + erpnext v16.51.1 + application_office into CUSTOM_IMAGE:CUSTOM_TAG
make up               # mariadb, redis, backend, workers, scheduler, edge (nginx), create-site, docuseal   (MODE=dev default)
make status
```
First run: `create-site` runs `bench new-site … --install-app erpnext --install-app application_office`. Then log in as
`Administrator` with `ADMIN_PASSWORD` from `.env`, complete the ERPNext Setup Wizard (**pick Arabic as the language**; company, country, **currency, chart of accounts, tax** - nothing is assumed by this platform), then:
1. Create the outgoing **Email Account** (required - without it every notification logs `Error`).
2. `AO Settings`: office name, **reviewed** disclaimer, terms/privacy URLs, retention, DocuSeal (optional).
3. Create staff users with AO roles; each staff member enrols 2FA at first login (enabled per role).
4. Create your `AO Program` records and **publish** them (requires a verification date).

**`host_name` must be the public HTTPS origin** (set by `create-site`; for an existing site run `bench --site <site> set-config host_name https://<site>`). Without it, set-password and notification links are built with the wrong origin (found during the browser E2E).

Environment variables: see `.env.example` (every variable commented). Secrets never go in Git (`.gitignore` covers `.env`, backups, `upstream/`).
Databases and Redis have no published ports; only `edge` is published (127.0.0.1:8088 in dev; 80/443 in prod). Resource limits are set in `compose.yaml` for backend, DocuSeal and its DB - tune after measuring.

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
