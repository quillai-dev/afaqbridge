# Implementation plan and status

Legend: ✅ implemented **and exercised by tests that were executed** · 🟡 implemented, not fully verified · ⛔ not implemented.

| Phase | Item | Status |
|---|---|---|
| 1 Investigation | clone/pin 5 required repos (+frappe_docker), licences, requirements, capability matrix | ✅ (licence review = headers only) |
| 2 Infrastructure | native dev stack (MariaDB 10.11, Redis, bench, ERPNext site) running; `make dev-site` reproduces it | ✅ |
| 2 | Docker Compose deployment, TLS proxy, health checks, resource limits | 🟡 written, YAML-validated, **never started** |
| 3 Core | DocTypes, workflow engine, roles/permissions, audit, retention, program/deadline mgmt | ✅ |
| 3 | Employee workspace: Desk lists/forms, case action buttons, final checklist, reveal-intake | 🟡 (buttons not browser-tested) |
| 3 | Desk **Workspace page and Script Reports** (case overview, review queue, missing documents) | ⛔ |
| 4 Portal | register/invite/consent, services, intake, upload, feedback, re-upload, approval, messages, invoices, data requests, receipts | ✅ API; 🟡 UI (JS syntax-checked and served; **no browser/UI test**) |
| 5 Integrations | DocuSeal client + webhook | ✅ vs simulator · 🟡 vs real DocuSeal (never run) |
| 5 | Helpdesk, Paperless-ngx, Nextcloud | ⛔ deferred by decision (architecture.md) |
| 6 | E-mail notifications, deadline reminders, invoice reminders, delivery status | ✅ |
| 6 | Telegram; payment-provider integration; operational reports | ⛔ |
| 7 Security | in-app tests, HTTP security tests, backup/restore drill | ✅ |
| 7 | vulnerability/image scanning, pen-test, TLS verification | ⛔ |
| 8 | README, docs, Makefile | ✅ (this set) |

## Test results (executed 2026-10-20 on the dev site)
- `make dev-test` → **Ran 61 tests … OK** (workflow, isolation/permissions, documents/uploads, registration/consent/MFA/rate-limit,
  notifications/reminders, finance on real ERPNext invoices+payments, DocuSeal vs simulator, retention/erasure).
- `make dev-http-test` → **Ran 14 tests … OK** against a real running server (sessions, CSRF, REST API closure, private-file URLs,
  upload rejection, lock-out, registration uniformity + rate-limit, SMTP-sink delivery, DocuSeal webhook rejection).
- Backup → encrypted archive → restore into scratch site → identical record counts (44 cases, 266 audit events, 137 customers, 37 files…). Wrong passphrase → `bad decrypt`.
Skipped tests: none. Mocks: only the simulated DocuSeal HTTP server (disclosed in the test module) and a local SMTP sink.
