# Docker deployment rehearsal (to be run by you - NOT yet executed)

The build sandbox had no Docker daemon and could not reach Docker Hub/ghcr.io/rubygems.org, so **no container of this project has ever been started**
and **real DocuSeal has never been run**. This is the exact procedure that closes those gaps. Use a disposable Linux host (Docker ≥ 24, Compose v2, ≥ 4 GB RAM, ports 80/443, a DNS name or `/etc/hosts` entry).

```
git clone <repo> application-office && cd application-office
git clone https://github.com/frappe/frappe_docker upstream/frappe_docker && git -C upstream/frappe_docker checkout df2a3b72910634cf0e878b59eccf68a93736bf9d
# push apps/application_office to a Git remote; put its URL in deploy/apps.json
make setup                       # .env with random secrets; then edit SITE_NAME, SITES_RULE, DOCUSEAL_HOST, CUSTOM_IMAGE/TAG
printf '%s' "$(openssl rand -base64 32)" > /root/.ao-backup-pass && chmod 600 /root/.ao-backup-pass
TEST_SITE=rehearsal.example.com scripts/rehearsal-docker.sh      # runs the checks below, writes rehearsal-evidence-<ts>.log
```
`scripts/rehearsal-docker.sh` checks: Docker present, `.env` present (aborts otherwise - verified to refuse to fake success), merged config renders, image builds,
stack starts, services healthy (empty status output counts as failure), `/api/method/ping` and `/office-portal` over HTTPS, HTTP→HTTPS redirect, `Secure` cookie flag,
MariaDB/Redis not reachable from the host, app tests in the container, encrypted backup.

## Then do by hand (the script does not cover these)
1. ERPNext setup wizard; Email Account; `AO Settings`; create staff + enrol 2FA through the real QR screen.
2. **Real DocuSeal:** open `https://$DOCUSEAL_HOST`, create admin, API token, a template, a webhook to `https://$SITE_NAME/api/method/application_office.integrations.docuseal.webhook`; set URL/token/secret in `AO Settings`; run one case through signing; confirm the webhook returns 200 and the signed PDF appears as a **private** file. Confirm the actual image tag name exists (`DOCUSEAL_TAG`).
3. Point `tests/e2e/e2e.mjs` at the host (it currently targets `http://office.localhost:8000` and the simulator) and re-run the browser flow against real DocuSeal with a real browser.
4. `make backup`, tamper a copy, confirm refusal; restore into a scratch site; compare counts.
5. Run a vulnerability scan on the built images (e.g. Trivy) and the dependency tree; record results.
6. Review `docs/security-model.md` "Not done" and close each item or accept it in writing.

Only after steps 1-6 pass and the evidence is archived may anyone call this deployment production-ready.
