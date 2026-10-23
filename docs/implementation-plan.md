# Implementation plan and status

Legend: ✅ implemented **and exercised by tests that were executed** · 🟡 implemented, not fully verified · ⛔ not implemented.

| Phase | Item | Status |
|---|---|---|
| 1 Investigation | clone/pin 5 required repos (+frappe_docker), licences, requirements, capability matrix | ✅ (licence review = headers only) |
| 2 Infrastructure | native dev stack (MariaDB 10.11, Redis, bench, ERPNext site) running; `make dev-site` reproduces it | ✅ |
| 2 | Docker Compose deployment, TLS proxy, health checks, resource limits | 🟡 written, YAML-validated, **never started** |
| 3 Core | DocTypes, workflow engine, roles/permissions, audit, retention, program/deadline mgmt | ✅ |
| 3 | Employee workspace: Desk lists/forms, Workflow/Review/Finance menus, final checklist, manual-submission form | ✅ browser-tested (reveal-intake button, add-message and evidence attach NOT browser-tested) |
| 3 | Desk **Workspace page and Script Reports** (case overview, review queue, missing documents) | ⛔ |
| 4 Portal | register/invite/consent, services, intake, upload, feedback, re-upload, approval, signing redirect, invoices, submission record | ✅ API + browser E2E (data requests, messages, receipt download, invite flow NOT browser-tested) |
| 5 Integrations | DocuSeal client + webhook | ✅ vs simulator · 🟡 vs real DocuSeal (never run) |
| 5 | Helpdesk, Paperless-ngx, Nextcloud | ⛔ deferred by decision (architecture.md) |
| 6 | E-mail notifications, deadline reminders, invoice reminders, delivery status | ✅ |
| 6 | Telegram; payment-provider integration; operational reports | ⛔ |
| 7 Security | in-app tests, HTTP security tests, backup/restore drill | ✅ |
| 7 | vulnerability/image scanning, pen-test, TLS verification | ⛔ |
| 8 | README, docs, Makefile | ✅ (this set) |

## Test results (executed 2026-10-22 on the dev site, current code)
| Suite | Command | Result |
|---|---|---|
| In-app (workflow, isolation, documents, registration/MFA/rate-limit, notifications, finance, DocuSeal-vs-simulator, retention) | `make dev-test` | **61 tests, OK** |
| HTTP-level security (real server) | `make dev-http-test` | **14 tests, OK** |
| Browser E2E (real headless Chromium 153) | `tests/e2e/run-e2e.sh` | **23/23 checks passed**; 10/10 notifications `Sent` and 10 mails received by the SMTP sink |
| Backup tamper drill | see docs/backup-restore.md | 7/7 tamper cases refused, pristine verifies |
| Compose static validation | `docker compose ... config` (Compose v2.40.3 binary) | renders; only the proxy publishes ports |
No test was skipped. Disclosed substitutes: a **simulated DocuSeal** (`tests/e2e/docuseal_sim.py`, `test_docuseal.py`) and a local **SMTP sink**.

### What the browser E2E covers (customer + three staff roles, 4 browser contexts)
Guest sees disclaimer → registers → receives set-password mail → signs in → starts case → intake → uploads (fake PDF rejected) → sends to office →
reviewer (2FA with TOTP) saves reviews in Desk, requests correction via Workflow menu → customer sees feedback, re-uploads → re-review → ready for approval →
customer approves (does **not** advance: signature pending) → redirected to simulated signing page → signed webhook processed by the real background worker →
READY_FOR_SUBMISSION → case worker runs final checklist, records the manual official submission → SUBMITTED → AWAITING_OFFICIAL_UPDATE →
finance sees no workflow menu and creates a draft invoice from the case → invoice submitted → COMPLETED → CLOSED → customer sees invoice, submission record
("not an acceptance" wording) and closed status.

### Known E2E limitations (be careful quoting these results)
- DocuSeal is a **simulator**; the real product was never run.
- **Invoice submission is not a browser step**: ERPNext's Sales Invoice form froze/crashed headless Chromium in this 1-CPU sandbox, so the draft is created through the Desk dialog and submitted server-side as the finance user (payment entries are covered by `test_finance`).
- Some Desk steps set values through Frappe's form object (`cur_frm.set_value`) instead of typing (submission timestamp).
- Not browser-tested: evidence attachment, receipt download, staff 2FA *enrolment* (OTP secrets are pre-provisioned by the harness), messages, data requests, invite flow, deadline and overdue-invoice reminders (the latter two are covered in-app).
- Chromium is an npm-bundled build (`@sparticuz/chromium`), not a user browser: no cross-browser or mobile testing.
