# Migration and rollback (existing deployment → AfaqBridge + nginx edge)

Nothing here deletes or recreates data. New named volumes only: `letsencrypt`, `acme-webroot`. Existing volumes (`sites`, `db-data`, `redis-*`, `docuseal-*`) are untouched as long as
**`COMPOSE_PROJECT_NAME` stays the same** (volumes are prefixed with it; `.env.example` pins `application-office`) - check `docker volume ls` before and after.

## Migrate
1. **Backup first**: `make backup` (encrypted) and copy it off-host. Note `docker compose ps` and `docker volume ls`.
2. `git pull`; merge new variables into `.env` (`diff .env .env.example`): `SITE_URL`, `DOCUSEAL_FORCE_SSL`, `EDGE_*`, `TLS_CERT_NAME`, `CERTBOT_IMAGE`; remove `SITES_RULE`. **Keep `SITE_NAME` as is.**
3. `make validate MODE=prod` (no side effects).
4. Traefik owns 80/443 today, so **there is a short gap** (seconds): `make down` (stops containers; **never** `down -v`), then `make up MODE=prod` → bootstrap edge → `make tls-issue MODE=prod`.
   Already-valid certificates can be copied into the `letsencrypt` volume (`live/<TLS_CERT_NAME>/`) to avoid re-issuing (Traefik's `acme.json` is *not* readable by certbot).
5. `make apply-branding` (idempotent). Verify: `curl -I https://<SITE_NAME>/login` → 200; log in; open the portal; AR/EN switch; one DocuSeal signing link (DocuSeal now needs `DOCUSEAL_FORCE_SSL` and its public URL unchanged).

## Roll back
1. `make down` (keeps volumes).
2. `git checkout <previous commit>` (restores `compose.yaml`, the old `.env.example`; restore your saved `.env`), then start the old stack with its own Makefile: `make up`.
3. Data needs no restore: the new version only changed settings (language, branding, 2 navbar items, `-ar` notification templates, languages other than ar/en disabled). To undo these on the site: set System Settings → Language back, Website Settings → *Show Language Picker* off, re-enable languages in the Language list; remove `*-ar` AO Notification Templates if unwanted.
4. Only if the site is damaged: restore the encrypted backup from step 1 with `scripts/restore.sh` into a **new** site name and compare before switching (the MAC cannot detect rollback to an older genuine backup).
