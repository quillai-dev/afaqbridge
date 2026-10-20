# Licence audit

**Not legal advice.** Licence identification below comes from the licence files/headers in the pinned clones
(read on 2026-10-20); full texts were not reviewed line-by-line. Have counsel confirm before commercial launch.

| Project | Licence (observed) | Used how | Obligation that matters for this deployment |
|---|---|---|---|
| Frappe v16.52.0 | MIT | runtime framework | notice retention |
| ERPNext v16.51.1 | GPL-3.0 | runtime app; our app is a separate Frappe app on top | GPLv3 applies to **distribution** (e.g. publishing a container image): corresponding source must be offered. Pure SaaS hosting without distributing copies does not trigger it |
| `application_office` (this repo) | MIT (`hooks.py: app_license`) | custom app | MIT is GPL-compatible; the *combined image* is distributed under GPLv3 terms - keep this app's source available if you ship images |
| Helpdesk v1.31.0 | AGPL-3.0 | **not deployed** | if later deployed *and modified*, AGPL §13 requires offering source to network users |
| DocuSeal 3.3.2 | AGPL-3.0 **+ Additional Terms** (§7(b)): *"a covered work must retain the original DocuSeal attribution in interactive user interfaces"* | separate service, used only through its REST API/webhooks; **unmodified** | do not strip attribution from signing UI; unmodified use → no source-offer duty, but any modification you make and expose over the network must be offered to its users. Some DocuSeal features are commercial-only upstream - **unverified**; confirm which features your plan needs |
| Paperless-ngx v3.3.2 | GPL-3.0 | deferred | - |
| Nextcloud v35.0.2 | AGPL-3.0 | deferred | - |
| `frappe_docker` (pinned `df2a3b72`) | MIT | compose/build recipes | notice retention |
| Python deps (pypdf, requests, aiosmtpd, …) | permissive (BSD/MIT/Apache) per PyPI metadata - **not scanned** | runtime/dev | run `pip-licenses` / SBOM tool in CI (**not done**) |

Not done: dependency & image vulnerability scan (no scanner run), SBOM generation, Docker image licence review.
