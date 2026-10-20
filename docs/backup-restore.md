# Backup and restore

## What is backed up
Frappe site: database dump, public files, **private files** (identity documents, evidence), `site_config`. DocuSeal: Postgres dump (`pg_dump`) and its data volume.
Archives are encrypted client-side: `openssl enc -aes-256-cbc -pbkdf2 -iter 600000` with a passphrase file stored **outside** the repo/backup directory
(password manager + offline copy - losing it makes every backup unreadable). A `.sha256` file detects corruption.

## Verified procedure (dev bench)
```
BACKUP_PASSPHRASE_FILE=/path/pass scripts/backup.sh office.localhost            # → ~/ao-backups/<site>-<ts>.tar.enc
BACKUP_PASSPHRASE_FILE=/path/pass DB_ROOT_PASSWORD=… scripts/restore.sh <file.tar.enc> scratch.localhost
```
Drill result (2026-10-20): restored into `restore-test.localhost`; counts identical to the source for cases, documents, audit events, customers, users, files; wrong passphrase → `bad decrypt`.
*Not demonstrated:* tamper detection through `restore.sh` (it runs `sha256sum -c` on the stored path; verify yourself), restore of DocuSeal, restore from the container deployment.

## Production
`make backup` → `scripts/backup-prod.sh` (docker compose exec; **unverified**). Schedule it (cron/systemd timer) at least daily, copy off-host, and
**rehearse a restore monthly**. Restore is intentionally manual: restore into a scratch site, inspect, then cut over (`scripts/restore-prod.sh` prints this and exits non-zero).

## Retention and deletion
Keep backups for the period declared in `AO Settings → backup_retention_note`. Case deletion/erasure does **not** rewrite backups; deleted personal data
remains in older backups until they are destroyed. Tell customers this (privacy notice). If you must purge a backup, delete the whole archive.
