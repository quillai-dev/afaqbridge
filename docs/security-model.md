# Security model

## Trust boundaries & roles
Customers (Website Users, role `Customer`) have **no** DocType permissions on any `AO *` record; they only call
whitelisted `portal_api.*` methods that re-derive the customer from the session and verify ownership of every object.
Foreign and non-existent ids are indistinguishable (404). Staff roles: `AO Administrator`, `AO Case Worker`,
`AO Reviewer`, `AO Finance` (+ ERPNext `Accounts User`), `AO Auditor`.

| | Cases | Documents | Review | Submission | Invoices | Settings/Retention |
|---|---|---|---|---|---|---|
| Case worker | own + unassigned, rw | own + unassigned, rw | read | create/rw | read | - |
| Reviewer | all, rw | all, rw | create | read | - | - |
| Finance | all, read | **none** | - | read | rw (ERPNext) | - |
| Auditor | all, read | **none** | read | read | read | - |
| Administrator | all | all | create | rw | rw | rw, deletion/erasure |

## Controls implemented and how they were verified
| Control | Evidence |
|---|---|
| Customer isolation (case, documents, uploads, messages, approval, signing URL, REST API, `frappe.client.*`, private file URLs) | in-app `test_isolation`, HTTP `test_http` |
| Row-level staff access; role matrix | `test_isolation` |
| CSRF on state-changing calls (missing & wrong token) | HTTP test. **Upstream caveat:** Frappe skips CSRF for a session that has no token yet; the portal fetches the token at start-up |
| Upload validation: ext allow-list, magic bytes, size, unreadable/encrypted PDF, PDF with JS/Launch/EmbeddedFile, private storage, server-generated names | `test_documents`, HTTP upload test. **Heuristic only** - not malware scanning |
| Optional ClamAV scan (fail-closed) | implemented, **untested** |
| Sensitive intake fields encrypted at rest (site key) and masked; reveal audited | `test_isolation` |
| Append-only audit; secrets/passport keys scrubbed from details | `test_workflow` |
| Rate limits: registration per IP (HTTP-tested → 429), per-user limits on uploads/messages/cases | HTTP + `TestRateLimit` |
| Login lock-out (per user and per IP), per-role 2FA for all staff roles, customers not forced | HTTP test; `TestMFA`. NB lock-out is reported by Frappe as HTTP 500 |
| Account enumeration: identical response for new/existing e-mail | HTTP test |
| Welcome/set-password mail via queue (outage cannot break registration) | HTTP test through SMTP sink |
| Webhook auth: HMAC, timestamp window, dedupe, size cap | `test_docuseal` |
| Human-only submission records | `test_workflow` |
| Session cookie `HttpOnly`, `SameSite`; `Secure` only over HTTPS | HTTP test (HttpOnly/SameSite); Secure **unverified** (needs TLS proxy) |
| XSS: portal JS never uses innerHTML/eval | static check in HTTP test |

## Not done / residual risk
TLS and HSTS (proxy config only, **never run**); CSP headers; encryption at rest (use LUKS/encrypted volumes - host
concern); dependency/image vulnerability scanning; SIEM/alerting; penetration test; DocuSeal/MariaDB hardening;
off-host backup storage; the reverse proxy must **overwrite** `X-Forwarded-For` or IP lock-outs/rate limits can be evaded.
Passport scans are stored as private files on the Frappe volume; anyone with host/volume access can read them
unless the volume is encrypted.

## Incident response (minimum)
1. Contain: `bench --site <site> set-config maintenance_mode 1`; rotate `ADMIN_PASSWORD`, DocuSeal token/secret, DB password.
2. Preserve: take an encrypted backup; export `AO Audit Event` and web/proxy logs.
3. Assess: which customers/documents were exposed (audit events `document.downloaded`, `intake.revealed`).
4. Notify: authorities/customers as required by the jurisdictions you operate in (deadlines can be as short as 72 h) - **your counsel decides**.
5. Review and add a regression test.

## Data protection
Consent captured per type + policy version; policy version bump forces re-consent. Retention periods per category in
`AO Settings`; eligible cases are flagged daily, never auto-deleted; deletion is admin-only, audited, blocked by legal
hold; erasure refuses while any case still needs retaining. **Backups are not rewritten**: deleted data persists in
backups until they expire (state your backup retention in `AO Settings`). The office must determine its own legal
obligations; the default disclaimer is a placeholder and does not make regulated activity lawful.
