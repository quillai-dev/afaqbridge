# Data model

Generated from the DocType JSON in `apps/application_office/.../doctype/` by this script (see git history). ERPNext `Customer` and `Sales Invoice`/`Payment Entry` are used as-is plus the custom fields listed at the end.


## AO Application Case  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `customer` | Link | required; → Customer |
| `customer_name` | Data | system-managed |
| `program` | Link | required; → AO Program |
| `service_type` | Data | system-managed |
| `case_state` | Select | system-managed; options: NEW / WAITING_FOR_DOCUMENTS / UNDER_REVIEW / CORRECTION_REQUIRED / READY_FOR_CUSTOMER_APPR |
| `assigned_employee` | Link | → User |
| `priority` | Select | options: Low / Normal / High / Urgent |
| `opening_date` | Date | required |
| `applicable_deadline` | Datetime |  |
| `deadline_time_zone` | Data | system-managed |
| `closure_date` | Date | system-managed |
| `internal_notes` | Text Editor |  |
| `customer_visible_notes` | Text Editor |  |
| `customer_approval_required` | Check |  |
| `final_customer_approval_status` | Select | system-managed; options: Not Requested / Requested / Approved / Changes Requested |
| `approved_by_user` | Link | system-managed; → User |
| `approved_on` | Datetime | system-managed |
| `approved_data_hash` | Data | system-managed |
| `official_submission_timestamp` | Datetime | system-managed |
| `official_confirmation_reference` | Data | system-managed |
| `intake_completed` | Check | system-managed |
| `intake_data` | Long Text | system-managed |
| `retention_until` | Date | system-managed |
| `legal_hold` | Check |  |
| `deletion_status` | Select | system-managed; options:  / Eligible / Deleted |
| `state_log` | Table | system-managed; → AO Case State Log |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (rw), AO Finance (r), AO Reviewer (rw), System Manager (r)

## AO Audit Event  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `event_time` | Datetime | required |
| `actor` | Data |  |
| `action` | Data |  |
| `ref_doctype` | Data |  |
| `ref_name` | Data |  |
| `case` | Data |  |
| `details` | Long Text |  |

_Permissions (level 0):_ AO Administrator (r), AO Auditor (r)

## AO Case Message  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `case` | Link | required; → AO Application Case |
| `visibility` | Select | required; options: Internal / Customer |
| `direction` | Select | required; options: Staff / Customer |
| `author` | Link | required; → User |
| `body` | Long Text | required |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (rw), AO Reviewer (rw)

## AO Case State Log  _(child table)_

| Field | Type | Notes |
|---|---|---|
| `from_state` | Data | system-managed |
| `to_state` | Data | system-managed |
| `actor` | Data | system-managed |
| `changed_at` | Datetime | system-managed |
| `reason` | Small Text | system-managed |

## AO Consent Record  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `customer` | Link | required; → Customer |
| `user` | Link | → User |
| `consent_type` | Select | required; options: Terms of Service / Privacy Notice / Sensitive Data Processing / Electronic Signature / Mar |
| `policy_version` | Data |  |
| `granted` | Check |  |
| `recorded_at` | Datetime | required |
| `withdrawn_at` | Datetime |  |

_Permissions (level 0):_ AO Administrator (r), AO Auditor (r), AO Case Worker (r)

## AO Data Request  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `customer` | Link | required; → Customer |
| `request_type` | Select | required; options: Access / Export / Correction / Erasure / Account Closure |
| `details` | Small Text |  |
| `status` | Select | options: Open / In Progress / Completed / Refused |
| `decision_note` | Small Text |  |
| `received_at` | Datetime | system-managed |
| `completed_at` | Datetime | system-managed |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (r)

## AO Document Review  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `required_document` | Link | required; → AO Required Document |
| `case` | Link | required; system-managed; → AO Application Case |
| `reviewer` | Link | required; system-managed; → User |
| `review_date` | Datetime | required; system-managed |
| `decision` | Select | required; options: Approved / Correction Required |
| `version_reviewed` | Int | required; system-managed |
| `findings` | Small Text |  |
| `requested_corrections` | Small Text |  |
| `customer_feedback` | Small Text |  |
| `review_completed` | Check |  |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (r), AO Reviewer (rw)

## AO Document Version  _(child table)_

| Field | Type | Notes |
|---|---|---|
| `version` | Int | system-managed |
| `file` | Data | system-managed |
| `original_filename` | Data | system-managed |
| `sha256` | Data | system-managed |
| `size_bytes` | Int | system-managed |
| `content_type` | Data | system-managed |
| `uploaded_by` | Data | system-managed |
| `uploaded_at` | Datetime | system-managed |

## AO Form Approval  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `case` | Link | required; → AO Application Case |
| `customer` | Link | system-managed; → Customer |
| `form_template` | Data | required |
| `approval_mode` | Select | required; options: In-Portal Approval / DocuSeal Signature |
| `submission_status` | Select | system-managed; options: Pending / Sent / Viewed / Completed / Declined / Expired / Error |
| `customer_approval` | Check | system-managed |
| `approval_timestamp` | Datetime | system-managed |
| `signature_status` | Select | system-managed; options: Not Applicable / Pending / Signed / Declined |
| `docuseal_template_id` | Data | system-managed |
| `docuseal_submission_id` | Data | system-managed |
| `docuseal_submitter_id` | Data | system-managed |
| `docuseal_signing_url` | Data | system-managed |
| `signed_document_file` | Data | system-managed |
| `last_error` | Small Text | system-managed |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (rw), AO Reviewer (r)

## AO Integration Event  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `event_key` | Data | required; unique |
| `source` | Data |  |
| `event_type` | Data |  |
| `status` | Select | options: Received / Processed / Error / Ignored |
| `attempts` | Int |  |
| `received_at` | Datetime |  |
| `error` | Small Text |  |
| `payload_digest` | Data |  |
| `context` | Small Text |  |

_Permissions (level 0):_ AO Administrator (r), AO Auditor (r)

## AO Notification Log  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `dedupe_key` | Data | required; unique |
| `event_key` | Data |  |
| `case` | Link | → AO Application Case |
| `customer` | Link | → Customer |
| `recipient` | Data |  |
| `status` | Select | options: Queued / Sent / Error / Skipped |
| `email_queue` | Data |  |
| `error` | Small Text |  |
| `sent_at` | Datetime |  |

_Permissions (level 0):_ AO Administrator (r), AO Auditor (r), AO Case Worker (r)

## AO Notification Template  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `event_key` | Data | required |
| `language` | Data | required |
| `enabled` | Check |  |
| `subject` | Data | required |
| `body` | Text Editor | required |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (r)

## AO Official Submission  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `case` | Link | required; → AO Application Case |
| `submitted_by` | Link | required; system-managed; → User |
| `human_submission_attestation` | Check | required |
| `official_portal` | Data | required |
| `submission_timestamp` | Datetime | required |
| `official_confirmation_number` | Data | required |
| `submission_status` | Select | required; options: Submitted / Confirmation Received / Follow-up Needed / Official Update Received |
| `follow_up_date` | Date |  |
| `evidence_file` | Attach |  |
| `customer_can_download_evidence` | Check |  |
| `official_correspondence` | Long Text |  |
| `customer_visible_update` | Small Text |  |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (rw), AO Finance (r), AO Reviewer (r)

## AO Program  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `program_name` | Data | required; unique |
| `program_category` | Select | required; options: Diversity Visa Lottery / Scholarship / Educational / Exchange Program / Other |
| `sponsoring_organization` | Data |  |
| `published` | Check |  |
| `service_available` | Check |  |
| `responsible_employee` | Link | required; → User |
| `last_verified_on` | Date | required |
| `verification_stale_after_days` | Int |  |
| `official_application_url` | Data |  |
| `official_requirements_url` | Data |  |
| `opening_datetime` | Datetime |  |
| `closing_datetime` | Datetime |  |
| `time_zone` | Data | required |
| `fee_amount` | Currency |  |
| `fee_note` | Small Text |  |
| `customer_approval_required` | Check |  |
| `eligibility_information` | Text Editor |  |
| `document_requirements` | Table | → AO Program Document Requirement |
| `intake_fields` | Table | → AO Program Intake Field |
| `form_templates` | Table | → AO Program Form Template |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (r), AO Finance (r), AO Reviewer (r)

## AO Program Document Requirement  _(child table)_

| Field | Type | Notes |
|---|---|---|
| `document_category` | Data | required |
| `required` | Check |  |
| `retention_category` | Select | options: Identity Document / Educational Record / Form / Approval / Submission Evidence / Financial |
| `instructions` | Small Text |  |

## AO Program Form Template  _(child table)_

| Field | Type | Notes |
|---|---|---|
| `form_name` | Data | required |
| `docuseal_template_id` | Data |  |
| `signature_required` | Check |  |

## AO Program Intake Field  _(child table)_

| Field | Type | Notes |
|---|---|---|
| `field_key` | Data | required |
| `label` | Data | required |
| `field_type` | Select | required; options: Text / Long Text / Date / Select / Checkbox |
| `required` | Check |  |
| `sensitive` | Check |  |
| `options` | Small Text |  |

## AO Referral  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `case` | Link | required; → AO Application Case |
| `reason` | Small Text | required |
| `referral_status` | Select | options: Proposed / Contacted / Accepted by Professional / Declined / Closed |
| `professional_or_organization` | Data | required |
| `jurisdiction` | Data | required |
| `customer_notified` | Check | system-managed |
| `licence_details` | Small Text | permlevel 1 (admin write) |
| `licence_verified` | Check | permlevel 1 (admin write) |
| `verified_by` | Link | system-managed; → User; permlevel 1 (admin write) |
| `verification_date` | Date | permlevel 1 (admin write) |
| `verification_source` | Data | permlevel 1 (admin write) |
| `communications` | Table | → AO Referral Communication |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (rw), AO Reviewer (r)

## AO Referral Communication  _(child table)_

| Field | Type | Notes |
|---|---|---|
| `communicated_on` | Datetime | required |
| `direction` | Select | options: To Professional / From Professional / To Customer |
| `summary` | Small Text | required |

## AO Required Document  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `case` | Link | required; → AO Application Case |
| `customer` | Link | system-managed; → Customer |
| `document_category` | Data | required |
| `required` | Check |  |
| `upload_status` | Select | system-managed; options: Not Uploaded / Uploaded |
| `review_status` | Select | system-managed; options: Pending / In Review / Approved / Correction Required |
| `current_version` | Int | system-managed |
| `reviewer` | Link | system-managed; → User |
| `review_timestamp` | Datetime | system-managed |
| `retention_category` | Select | options: Identity Document / Educational Record / Form / Approval / Submission Evidence / Financial |
| `instructions` | Small Text | system-managed |
| `rejection_reason` | Small Text | system-managed |
| `customer_feedback` | Small Text | system-managed |
| `versions` | Table | system-managed; → AO Document Version |

_Permissions (level 0):_ AO Administrator (rw), AO Case Worker (rw), AO Reviewer (rw)

## AO Retention Rule  _(child table)_

| Field | Type | Notes |
|---|---|---|
| `retention_category` | Select | required; options: Identity Document / Educational Record / Form / Approval / Submission Evidence / Financial |
| `years` | Int | required |

## AO Settings  _(single)_

| Field | Type | Notes |
|---|---|---|
| `office_name` | Data | required |
| `disclaimer_text` | Text Editor | required |
| `terms_url` | Data |  |
| `privacy_url` | Data |  |
| `terms_version` | Data | required |
| `privacy_version` | Data | required |
| `sensitive_data_consent_text` | Small Text | required |
| `max_upload_mb` | Int | required |
| `allowed_extensions` | Data | required |
| `clamav_socket` | Data |  |
| `reminder_days` | Data | required |
| `invoice_reminder_days` | Int |  |
| `retention_rules` | Table | → AO Retention Rule |
| `default_retention_years` | Int | required |
| `backup_retention_note` | Small Text |  |
| `docuseal_enabled` | Check |  |
| `docuseal_base_url` | Data |  |
| `docuseal_api_token` | Password |  |
| `docuseal_webhook_secret` | Password |  |
| `docuseal_signer_role` | Data |  |
| `service_accounts` | Small Text |  |

_Permissions (level 0):_ AO Administrator (rw), System Manager (rw)

## AO Workflow Transition  _(doctype)_

| Field | Type | Notes |
|---|---|---|
| `from_state` | Select | required; options: NEW / WAITING_FOR_DOCUMENTS / UNDER_REVIEW / CORRECTION_REQUIRED / READY_FOR_CUSTOMER_APPR |
| `to_state` | Select | required; options: NEW / WAITING_FOR_DOCUMENTS / UNDER_REVIEW / CORRECTION_REQUIRED / READY_FOR_CUSTOMER_APPR |
| `allowed_roles` | Data | required |
| `requires_reason` | Check |  |
| `notification_event` | Data |  |
| `enabled` | Check |  |

_Permissions (level 0):_ AO Administrator (rw), AO Auditor (r), AO Case Worker (r)

## ERPNext custom fields (created by `install.py`)
- Customer: `ao_customer_reference` (unique), `ao_account_status` (Active/Invited/Suspended/Closed), `ao_phone`
- Sales Invoice: `ao_application_case` (Link → AO Application Case)

## Workflow
States: NEW, WAITING_FOR_DOCUMENTS, UNDER_REVIEW, CORRECTION_REQUIRED, READY_FOR_CUSTOMER_APPROVAL, READY_FOR_SUBMISSION, SUBMITTED, AWAITING_OFFICIAL_UPDATE, COMPLETED, ON_HOLD, CANCELLED, REJECTED_BY_OFFICIAL_AUTHORITY, CLOSED.
Transitions, allowed roles, reason requirement and the customer notification fired are rows of `AO Workflow Transition` (33 seeded; editable by administrators). Hard guards in code: documents approved + intake complete before approval; customer approval + unchanged data hash (+ signatures) before READY_FOR_SUBMISSION; an employee-entered Official Submission before SUBMITTED. Returning to review/correction resets approval. `COMPLETED` = office service done; an official outcome is only ever recorded as `REJECTED_BY_OFFICIAL_AUTHORITY`/notes - the platform never infers acceptance.
