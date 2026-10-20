# Operations

**Daily:** `make status`; check `AO Notification Log` for `Error` rows (usually mail account problems); `AO Integration Event` rows in `Error` (retried hourly ≤5×).
**Scheduler jobs (hourly):** deadline reminders (tightest crossed threshold per case, once), mail delivery-status sync, DocuSeal event retry. **(daily):** overdue-invoice reminders, retention eligibility flagging.
Frappe holds queued mail ~10 s before it is eligible to send; mail is flushed by the scheduler.

## Common tasks
| Task | How |
|---|---|
| Create a staff user | Desk → User → add roles (AO …; Finance also needs `Accounts User`); user enrols 2FA at first login |
| Invite a customer | `bench --site <s> execute application_office.staff_api.invite_customer --kwargs '{"email":"…","full_name":"…"}'` as an authorised user, or the customer self-registers at `/office-portal` (no Desk button yet) |
| Update a program | Desk → AO Program; **update “last verified on”** after checking the official site. Programs stale beyond the configured days become non-startable |
| Move a case | Desk → case → *Workflow* menu (only valid transitions for your role are offered) |
| Record a submission | after submitting on the official site yourself: case in READY_FOR_SUBMISSION → *Submission → Record Manual Official Submission*; tick the attestation, enter confirmation number, attach evidence (private) |
| Referral | New `AO Referral`; only an AO Administrator can set *licence verified* (needs source + details) |
| Delete case data | after retention: AO Administrator runs `staff_api.delete_case_data` (flagged cases get a ToDo). Legal hold blocks it |
| Customer data request | `AO Data Request` list; erasure via `application_office.retention.execute_erasure` (refuses while cases must be retained) |
| Rotate DocuSeal secret/token | AO Settings + DocuSeal webhook settings together; test with a dummy signing |

## Known behaviours to expect
- Frappe returns **HTTP 500** for a login lock-out and for unknown static `/files/…` on the dev server (nginx returns 404 in production).
- New-user creation is throttled by Frappe (`throttle_user_limit`, default 60/h) - raise only deliberately.
- Case workers see only their cases + unassigned; assign cases or they pile up in a shared pool.
