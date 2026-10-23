# Application Office Platform

Self-hosted workflow platform for an office that **assists customers with applications** (DV lottery, scholarships such as
Erasmus Mundus / DAAD, exchange programs, other configurable services). Customers submit information and documents; employees review,
prepare and **personally submit on the official website**. The software never logs in to, scrapes, or submits to any official site.
It is administrative software, not legal advice, and guarantees no outcome (configurable disclaimer; referral workflow with *staff-verified* licence data).

Built by reusing **ERPNext/Frappe** (system of record) + a custom Frappe app `application_office` + **DocuSeal** (optional e-signature).
Helpdesk, Paperless-ngx and Nextcloud were evaluated and **deliberately deferred** (docs/architecture.md).

## Honest status (read this first)
| | |
|---|---|
| Core app on real ERPNext v16.51.1 / Frappe v16.52.0 | ✅ running in the dev sandbox |
| Automated tests executed | ✅ 61 in-app + 14 HTTP + 23-check browser E2E, all passing (2026-10-22), none skipped |
| Backups | ✅ encrypted + HMAC-authenticated; 7/7 tamper cases refused; restore drills done (counts compared on the old format only) |
| DocuSeal | 🟡 client + HMAC webhook implemented; tested **only against a simulator** (in-app tests + browser E2E) - never run against real DocuSeal (blocked: no Docker/rubygems in the build sandbox) |
| Docker Compose deployment | 🟡 written from pinned `frappe_docker`; merged config validated with the real Compose v2.40.3 binary; **never started**. Run `scripts/rehearsal-docker.sh` on a Docker host (docs/rehearsal-docker.md) |
| Customer portal + Desk UI | ✅ driven end-to-end in a real headless Chromium (customer, reviewer, case worker, finance); invoice *submission* not a browser step (see implementation-plan) |
| Desk Workspace page / Script Reports | ⛔ not built (lists, forms and action buttons exist) |
| Helpdesk / Paperless / Nextcloud / Telegram | ⛔ not implemented (deferred) |
| Vulnerability scanning, TLS verification, pen-test | ⛔ not done |
Full table: [docs/implementation-plan.md](docs/implementation-plan.md). **Do not run production on this before the unverified items are rehearsed.**

## Layout
```
apps/application_office/   custom Frappe app (DocTypes, workflow, portal API, staff API, integrations, tests)
deploy/apps.json           apps baked into the production image
compose.yaml               office layer (DocuSeal, create-site, limits) on top of upstream/frappe_docker overrides
upstream/                  pinned clones (git-ignored): frappe, erpnext, frappe-helpdesk, docuseal, paperless-ngx, nextcloud, frappe_docker
scripts/                   dev stack, backup/restore, secrets, pin report, generators
tests/http/                HTTP-level security tests          docs/   audits, architecture, security, operations
```
`upstream/` is not committed: re-create it from the table in docs/repository-audit.md (remote + tag + commit).

## Commands
`make help` lists everything. Verified: `dev-up dev-site dev-test dev-http-test dev-backup`. Container targets
(`setup image up down logs status test backup restore`) need Docker and refuse to run without it.

## First administrator
`bench new-site … --admin-password <strong>` creates `Administrator` (container: password = `ADMIN_PASSWORD` in `.env`). Then in Desk:
complete the ERPNext Setup Wizard (company/currency/tax), create a personal admin User with roles **AO Administrator** (+ System Manager if needed),
log in as that user and enrol 2FA (enabled for every staff role), and stop using `Administrator` day-to-day.
Configure *Email Account* (mandatory) and *AO Settings* (disclaimer reviewed by a lawyer, terms/privacy URLs, retention).

## First customer
Self-registration at `https://<site>/office-portal` (name, e-mail, three consents) → the customer receives a one-time set-password link → signs in at `/login`.
Or staff invite (`staff_api.invite_customer`; the customer must accept the consents at first login). Registration is rate-limited and answers identically for existing addresses.

## Process one sample application end to end
(Exactly this sequence runs in `test_workflow.test_full_happy_path`.)
1. **Staff:** create `AO Program` (documents list, intake fields, optional DocuSeal template), set *last verified on*, **publish**.
2. **Customer:** portal → *Start* → fill the information form → upload each required document → *Send to our office for review* (state UNDER_REVIEW).
3. **Reviewer:** Desk → `AO Required Document` → review each (Approved / Correction Required + customer feedback). Corrections → customer re-uploads → repeat.
4. **Staff:** case → *Workflow → READY_FOR_CUSTOMER_APPROVAL* (guard: all required docs approved, intake complete); customer gets an e-mail.
5. **Customer:** reviews, ticks the confirmation, *Approve* (hash of intake+document versions is stored; signing via DocuSeal first if the program requires it).
6. **Employee:** case reaches READY_FOR_SUBMISSION; *Final Checklist*; **submit on the official website yourself**; then *Record Manual Official Submission* (attestation, portal, time, confirmation number, private evidence) → state SUBMITTED, customer notified (this is **not** an acceptance).
7. **Staff:** AWAITING_OFFICIAL_UPDATE → COMPLETED (or REJECTED_BY_OFFICIAL_AUTHORITY) as official news arrives; *Create Invoice* (Finance) → ERPNext Payment Entry; → CLOSED (retention date computed).
8. After retention: case flagged *Eligible*; an AO Administrator runs the audited deletion (legal hold blocks it).

## Known limitations
See docs/security-model.md ("Not done / residual risk") and docs/operations.md ("Known behaviours"). Notable: tested on MariaDB 10.11 while upstream containers use 11.8;
upload checks are heuristics (no malware scan unless ClamAV is configured and tested); notifications are e-mail only; failed notification rows are logged, not auto-resent;
the default legal disclaimer is a placeholder; licences were read from headers, not legally reviewed.

## Licences
This app: MIT. Combined with GPLv3 ERPNext and AGPLv3 + attribution-term DocuSeal - see [docs/license-audit.md](docs/license-audit.md).
