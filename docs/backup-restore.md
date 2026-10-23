# Backup and restore

## What is backed up
Frappe site: database dump, public files, **private files** (identity documents, evidence), `site_config`. DocuSeal: Postgres dump (`pg_dump`) and its data volume.
Archives are **encrypted then authenticated** (`scripts/lib-backup.sh`): AES-256-CBC (`openssl enc -pbkdf2 -iter 600000`) of the tar stream, plus `<file>.mac` = HMAC-SHA256 over the ciphertext keyed from the passphrase. `restore.sh` verifies the MAC **before** decrypting or creating any site, so tampering by someone without the passphrase is detected. `<file>.sha256` is only a transfer-corruption check. The passphrase file lives **outside** the repo/backup directory (password manager + offline copy - losing it makes every backup unreadable). Residual: an attacker who also holds the passphrase can forge a valid backup; a rollback to an *older genuine* backup of the same site is not detectable by the MAC alone (keep an off-host manifest of expected latest backup name/time).

## Verified procedure (dev bench)
```
BACKUP_PASSPHRASE_FILE=/path/pass scripts/backup.sh office.localhost            # → ~/ao-backups/<site>-<ts>.tar.enc
BACKUP_PASSPHRASE_FILE=/path/pass DB_ROOT_PASSWORD=… scripts/restore.sh <file.tar.enc> scratch.localhost
```
Drills (dev bench):
- 2026-10-20, original format: restored into a scratch site; counts identical (44 cases, 266 audit events, 137 customers, 37 files, 140 users).
- 2026-10-22, authenticated format: backup → restore into `restore2.localhost` completed ("restored into restore2.localhost"); **record counts were not compared for this run**.
- 2026-10-22 tamper drill, driven through the real `restore.sh`, each case expected **exit 3 and no site created**:

| # | Case | Result |
|---|---|---|
| 0 | pristine file (control) | verifies |
| 1 | flip one byte | refused |
| 2 | truncate | refused |
| 3 | replace file + recompute `.sha256` | refused |
| 4 | replace file + forge `.mac` with attacker's passphrase | refused |
| 5 | delete `.mac` | refused |
| 6 | correct file, wrong passphrase | refused |
| 7 | swap an older genuine backup in, keep new `.mac` | refused |

*Not demonstrated:* DocuSeal Postgres restore, restore from the container deployment, restore of the production script `backup-prod.sh` (never executed - no Docker).

## Production
`make backup` → `scripts/backup-prod.sh` (docker compose exec; **unverified**). Schedule it (cron/systemd timer) at least daily, copy off-host, and
**rehearse a restore monthly**. Restore is intentionally manual: restore into a scratch site, inspect, then cut over (`scripts/restore-prod.sh` prints this and exits non-zero).

## Retention and deletion
Keep backups for the period declared in `AO Settings → backup_retention_note`. Case deletion/erasure does **not** rewrite backups; deleted personal data
remains in older backups until they are destroyed. Tell customers this (privacy notice). If you must purge a backup, delete the whole archive.
