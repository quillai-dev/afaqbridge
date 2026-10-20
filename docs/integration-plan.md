# Integration plan

| Integration | Direction | Auth | Idempotency / retry | Status |
|---|---|---|---|---|
| Portal → Frappe | browser → `/api/method/application_office.portal_api.*` | Frappe session cookie + `X-Frappe-CSRF-Token` | per-user rate limits | **implemented, tested (HTTP + in-app)** |
| ERPNext Customer / Sales Invoice | in-process | Frappe permissions | n/a | **implemented, tested** |
| DocuSeal: create signing request | Frappe → DocuSeal `POST /api/submissions` | `X-Auth-Token` | one submission per Form Approval (stored URL reused); 3 tries on 5xx/connection error, then `Error` + staff retry | **implemented; tested only against a simulator** |
| DocuSeal: webhook | DocuSeal → `/api/method/application_office.integrations.docuseal.webhook` | HMAC-SHA256 header, ±300 s | `AO Integration Event.event_key` UNIQUE (`event_type:id:timestamp`) → duplicate = 200 "duplicate"; hourly retry of `Error` events (≤5) | **implemented; tested with signed synthetic payloads** |
| DocuSeal: fetch signed PDF | Frappe → DocuSeal API | `X-Auth-Token`; host must equal configured host (SSRF guard) | best effort; signature already recorded | implemented, simulator-tested |
| E-mail | Frappe Email Queue → SMTP | SMTP account | `AO Notification Log.dedupe_key` UNIQUE | **implemented; delivery proven against a local SMTP sink** |
| Helpdesk | - | - | - | **not implemented** (deferred) |
| Paperless-ngx | - | - | - | **not implemented** (deferred) |
| Nextcloud | - | - | - | **not implemented** (deferred) |
| Telegram | - | - | - | **not implemented** |

## DocuSeal setup (once DocuSeal is running)
1. In DocuSeal create an API token and a template whose signer role matches `AO Settings → DocuSeal signer role`.
2. In `AO Program → Forms & Signatures` add the template id and tick *signature required* if a signature is mandatory.
3. In DocuSeal add a webhook to `https://<site>/api/method/application_office.integrations.docuseal.webhook`, copy its `whsec_…` secret.
4. In `AO Settings` enable DocuSeal, set base URL (HTTPS), API token, webhook secret.
5. **Run an end-to-end test against the real instance** - this has not been done.

Signature legality varies by document and jurisdiction; the platform records signatures, it does not certify them.
