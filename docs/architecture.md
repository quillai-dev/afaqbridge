# Architecture

> Public entry point: ONE nginx `edge` (TLS, host routing, DocuSeal). Traefik was removed. Details: [deployment.md](deployment.md#0-web-entry-point-nginx-edge).

```
 Customer browser ──HTTPS──▶ nginx(edge) ──▶ nginx(frontend) ──▶ gunicorn(backend: Frappe + ERPNext + application_office)
 Staff browser    ──HTTPS──▶    │                                   │            │
 DocuSeal signer  ──HTTPS──▶    └──▶ DocuSeal (own host name) ──webhook (HMAC)──────┘            ├─ MariaDB   (internal network only)
                                        │  └─ Postgres (internal only)           ├─ Redis cache / queue
                                        └◀── REST (X-Auth-Token) ────────────────┴─ workers (short/long) + scheduler
```

**Decision: ERPNext/Frappe is the single system of record.** One Frappe site hosts ERPNext (customers, invoices,
payments, accounting), the custom `application_office` app (cases, programs, documents, reviews, workflow,
notifications, audit, retention) and the customer portal page. DocuSeal is a *separate* service reached only by
REST/webhook; no database is shared between applications.

| Entity | Authoritative source | Cross-system key |
|---|---|---|
| Customer / contact | ERPNext `Customer` | `ao_customer_reference` (CU-xxxxxxxx) |
| Case, program, documents, reviews, submissions, referrals | `application_office` | case name `AC-YYYY-#####` |
| Invoice / payment | ERPNext Sales Invoice / Payment Entry | custom field `ao_application_case` |
| Signature request / signed PDF | DocuSeal (source) → copy kept as private `File` | `AO Form Approval.name` sent as submitter `external_id`; DocuSeal ids stored on the approval |

## Deployed in the first release
ERPNext, `application_office`, DocuSeal (+Postgres) **optional but wired**, MariaDB, Redis, reverse proxy.

## Deliberately deferred (decisions, not omissions)
- **Frappe Helpdesk** - needs the extra `telephony` app and its own desk UI; the office's v1 need ("contact the office",
  correction requests, history) is covered by `AO Case Message` + notifications. Upstream ships an ERPNext sync module
  (`ERPNext HD Settings`) so adoption later is plausible, but compatibility with our permission model is **unverified**.
- **Paperless-ngx** - Frappe private files + retention jobs satisfy v1; adds OCR search later. Integration path: push
  approved PDFs via Paperless' REST API after case closure; not implemented.
- **Nextcloud** - no requirement not already met by private Frappe files; would duplicate storage and permissions.

## Human-submission boundary
Nothing in this system contacts an official website. `AO Official Submission` is created only by an authenticated
employee (role + System User + attestation checkbox; API-token requests and configured service accounts are refused).
The workflow state `SUBMITTED` means "an employee recorded a submission", never "accepted".

## Failure containment
DocuSeal outage → the form approval records `Error`, the customer sees a generic retry message, other cases are
unaffected, staff can re-run `sync_signing_request`. Webhooks are acknowledged fast and processed in a background job;
failed events are retried hourly up to 5 attempts. Mail outage → notification log row `Error`; registration/workflow
never fail because of mail (mail is queued, not sent inline).
