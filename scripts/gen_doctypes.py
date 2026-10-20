#!/usr/bin/env python3
"""Generate DocType JSON + empty controller stubs for application_office.

The JSON files under apps/application_office/.../doctype/ are the source of truth once
generated and are committed. Re-running this script overwrites JSON only (never an
existing controller .py), so it is safe for adding new DocTypes during development.
"""
import json
import os
import re
import sys

ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "apps", "application_office", "application_office", "application_office", "doctype",
)
MODULE = "Application Office"

ADMIN, WORKER, REVIEWER, FINANCE, AUDITOR = (
    "AO Administrator", "AO Case Worker", "AO Reviewer", "AO Finance", "AO Auditor",
)


def snake(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def F(fieldname, fieldtype="Data", label=None, **kw):
    d = {"fieldname": fieldname, "fieldtype": fieldtype,
         "label": label or fieldname.replace("_", " ").title()}
    d.update(kw)
    for k in ("reqd", "read_only", "in_list_view", "in_standard_filter", "unique", "hidden", "no_copy",
              "set_only_once", "search_index", "default"):
        if k in d and d[k] is True:
            d[k] = 1
        elif k in d and d[k] is False:
            d.pop(k)
    return d


def SEC(name, label=None):
    return F(name, "Section Break", label)


def COL(name):
    return F(name, "Column Break")


def perm(role, **rights):
    p = {"role": role, "permlevel": rights.pop("permlevel", 0)}
    for r in ("read", "write", "create", "delete", "report", "export", "print", "email", "share"):
        p[r] = 1 if rights.get(r) else 0
    return p


def RW(role, create=True, delete=False, **kw):
    return perm(role, read=1, write=1, create=1 if create else 0, delete=1 if delete else 0,
                report=1, export=1, **kw)


def RO(role, **kw):
    return perm(role, read=1, report=1, export=1, **kw)


def doctype(name, fields, permissions, **kw):
    d = {
        "doctype": "DocType", "name": name, "module": MODULE, "custom": 0, "engine": "InnoDB",
        "fields": fields, "permissions": permissions, "sort_field": "modified", "sort_order": "DESC",
        "track_changes": 1, "editable_grid": 1, "row_format": "Dynamic",
    }
    d.update(kw)
    if d.get("istable"):
        d["permissions"] = []
        d.pop("track_changes", None)
    return d


STATES = [
    "NEW", "WAITING_FOR_DOCUMENTS", "UNDER_REVIEW", "CORRECTION_REQUIRED",
    "READY_FOR_CUSTOMER_APPROVAL", "READY_FOR_SUBMISSION", "SUBMITTED",
    "AWAITING_OFFICIAL_UPDATE", "COMPLETED", "ON_HOLD", "CANCELLED",
    "REJECTED_BY_OFFICIAL_AUTHORITY", "CLOSED",
]
CATEGORIES = "Diversity Visa Lottery\nScholarship\nEducational / Exchange Program\nOther"
RETENTION = "Identity Document\nEducational Record\nForm / Approval\nSubmission Evidence\nFinancial\nOther"

D = []

# ---------------------------------------------------------------- settings
D.append(doctype("AO Settings", [
    SEC("s_general", "Legal Notices"),
    F("office_name", "Data", reqd=True),
    F("disclaimer_text", "Text Editor", reqd=True, description=
      "Shown to customers at registration, on every service and in the portal footer. Must state the "
      "office does not guarantee acceptance/selection/immigration outcomes and gives no legal advice "
      "unless appropriately authorised. Have a lawyer review it for your jurisdictions."),
    F("terms_url", "Data", label="Service Terms URL"),
    F("privacy_url", "Data", label="Privacy Notice URL"),
    F("terms_version", "Data", default="1", reqd=True),
    F("privacy_version", "Data", default="1", reqd=True),
    F("sensitive_data_consent_text", "Small Text", reqd=True),
    SEC("s_uploads", "Uploads"),
    F("max_upload_mb", "Int", default=10, reqd=True),
    F("allowed_extensions", "Data", default="pdf,jpg,jpeg,png", reqd=True,
      description="Comma separated. Content is also sniffed; extension alone is never trusted."),
    F("clamav_socket", "Data", description="Optional path of a clamd UNIX socket; if set, uploads are scanned"),
    SEC("s_notify", "Notifications & Reminders"),
    F("reminder_days", "Data", default="14,7,3,1", reqd=True,
      description="Days before the deadline (program time zone) at which reminders are sent"),
    F("invoice_reminder_days", "Int", default=7, description="Remind about invoices unpaid this many days after due date"),
    SEC("s_retention", "Retention"),
    F("retention_rules", "Table", options="AO Retention Rule"),
    F("default_retention_years", "Int", default=7, reqd=True),
    F("backup_retention_note", "Small Text", description=
      "Document how long backups are kept. Deleted data may persist in backups until they expire."),
    SEC("s_docuseal", "DocuSeal"),
    F("docuseal_enabled", "Check"),
    F("docuseal_base_url", "Data"),
    F("docuseal_api_token", "Password"),
    F("docuseal_webhook_secret", "Password", description="The whsec_... secret DocuSeal shows for the webhook"),
    F("docuseal_signer_role", "Data", default="First Party", description="Signer role name used in your DocuSeal templates"),
    SEC("s_security", "Staff Workflow"),
    F("service_accounts", "Small Text", description=
      "Comma separated user IDs that are integrations/bots. They may NEVER create Official Submission records."),
], [perm(ADMIN, read=1, write=1), perm("System Manager", read=1, write=1)], issingle=1))

D.append(doctype("AO Retention Rule", [
    F("retention_category", "Select", options=RETENTION, reqd=True, in_list_view=True),
    F("years", "Int", reqd=True, in_list_view=True),
], [], istable=1))

# ---------------------------------------------------------------- program
D.append(doctype("AO Program Document Requirement", [
    F("document_category", "Data", reqd=True, in_list_view=True),
    F("required", "Check", default=True, in_list_view=True),
    F("retention_category", "Select", options=RETENTION, default="Identity Document", in_list_view=True),
    F("instructions", "Small Text"),
], [], istable=1))

D.append(doctype("AO Program Intake Field", [
    F("field_key", "Data", reqd=True, in_list_view=True, description="Machine key, lowercase letters/digits/underscore"),
    F("label", "Data", reqd=True, in_list_view=True),
    F("field_type", "Select", options="Text\nLong Text\nDate\nSelect\nCheckbox", default="Text", reqd=True, in_list_view=True),
    F("required", "Check", in_list_view=True),
    F("sensitive", "Check", description="Encrypted at rest and masked in staff views until explicitly revealed (audited)"),
    F("options", "Small Text", description="One option per line (Select only)"),
], [], istable=1))

D.append(doctype("AO Program Form Template", [
    F("form_name", "Data", reqd=True, in_list_view=True),
    F("docuseal_template_id", "Data", in_list_view=True, description="Leave empty to use in-portal click approval"),
    F("signature_required", "Check", in_list_view=True, description=
      "If set the customer must complete the DocuSeal signing. Whether an e-signature is legally "
      "sufficient is determined by the office per document and jurisdiction."),
], [], istable=1))

D.append(doctype("AO Program", [
    F("program_name", "Data", reqd=True, unique=True, in_list_view=True),
    F("program_category", "Select", options=CATEGORIES, reqd=True, in_list_view=True, in_standard_filter=True),
    F("sponsoring_organization", "Data"),
    F("published", "Check", in_list_view=True, in_standard_filter=True,
      description="Customers can only start cases for published programs"),
    F("service_available", "Check", default=True, in_list_view=True,
      description="Master switch: the office is currently taking clients for this service"),
    COL("c1"),
    F("responsible_employee", "Link", options="User", reqd=True),
    F("last_verified_on", "Date", reqd=True, description=
      "Date staff last verified this program's official information. Never inferred automatically."),
    F("verification_stale_after_days", "Int", default=30),
    SEC("s_official", "Official Information (verified by staff)"),
    F("official_application_url", "Data", options="URL"),
    F("official_requirements_url", "Data", options="URL"),
    F("opening_datetime", "Datetime"),
    F("closing_datetime", "Datetime"),
    F("time_zone", "Data", reqd=True, default="UTC", description="IANA name, e.g. Europe/Berlin. Dates above are in this zone."),
    F("fee_amount", "Currency"),
    F("fee_note", "Small Text"),
    F("customer_approval_required", "Check", default=True),
    F("eligibility_information", "Text Editor"),
    SEC("s_req", "Required Documents"),
    F("document_requirements", "Table", options="AO Program Document Requirement"),
    SEC("s_intake", "Intake Form"),
    F("intake_fields", "Table", options="AO Program Intake Field"),
    SEC("s_forms", "Forms & Signatures"),
    F("form_templates", "Table", options="AO Program Form Template"),
], [RW(ADMIN, delete=True), RO(WORKER), RO(REVIEWER), RO(FINANCE), RO(AUDITOR)],
    autoname="field:program_name", naming_rule="By fieldname", title_field="program_name"))

# ---------------------------------------------------------------- case
D.append(doctype("AO Case State Log", [
    F("from_state", "Data", read_only=True, in_list_view=True),
    F("to_state", "Data", read_only=True, in_list_view=True),
    F("actor", "Data", read_only=True, in_list_view=True),
    F("changed_at", "Datetime", read_only=True, in_list_view=True),
    F("reason", "Small Text", read_only=True),
], [], istable=1))

D.append(doctype("AO Application Case", [
    F("customer", "Link", options="Customer", reqd=True, in_list_view=True, in_standard_filter=True, set_only_once=True),
    F("customer_name", "Data", read_only=True, fetch_from="customer.customer_name", in_list_view=True),
    F("program", "Link", options="AO Program", reqd=True, in_list_view=True, in_standard_filter=True, set_only_once=True),
    F("service_type", "Data", read_only=True, fetch_from="program.program_category"),
    COL("c1"),
    F("case_state", "Select", options="\n".join(STATES), default="NEW", read_only=True, in_list_view=True,
      in_standard_filter=True, no_copy=True, label="Workflow State",
      description="Changed only through the workflow engine (Actions menu)."),
    F("assigned_employee", "Link", options="User", in_standard_filter=True, in_list_view=True),
    F("priority", "Select", options="Low\nNormal\nHigh\nUrgent", default="Normal", in_standard_filter=True),
    SEC("s_dates", "Dates"),
    F("opening_date", "Date", default="Today", reqd=True),
    F("applicable_deadline", "Datetime", in_list_view=True, in_standard_filter=True, description=
      "Interpreted in the program's time zone. Staff-verified; copied from the program at creation and editable."),
    F("deadline_time_zone", "Data", read_only=True, fetch_from="program.time_zone"),
    F("closure_date", "Date", read_only=True),
    SEC("s_notes", "Notes"),
    F("internal_notes", "Text Editor", description="Staff only. Never shown to the customer or included in notifications."),
    F("customer_visible_notes", "Text Editor", description="Visible to the customer in the portal."),
    SEC("s_approval", "Customer Approval"),
    F("customer_approval_required", "Check", default=True),
    F("final_customer_approval_status", "Select",
      options="Not Requested\nRequested\nApproved\nChanges Requested", default="Not Requested", read_only=True),
    F("approved_by_user", "Link", options="User", read_only=True),
    F("approved_on", "Datetime", read_only=True),
    F("approved_data_hash", "Data", read_only=True, description="SHA-256 of the intake data + document versions the customer approved"),
    SEC("s_official", "Official Submission (recorded by a human employee)"),
    F("official_submission_timestamp", "Datetime", read_only=True),
    F("official_confirmation_reference", "Data", read_only=True),
    SEC("s_intake", "Intake Data"),
    F("intake_completed", "Check", read_only=True),
    F("intake_data", "Long Text", read_only=True, hidden=True),
    SEC("s_retention", "Retention"),
    F("retention_until", "Date", read_only=True),
    F("legal_hold", "Check", description="Blocks automatic deletion eligibility"),
    F("deletion_status", "Select", options="\nEligible\nDeleted", read_only=True),
    SEC("s_log", "State History"),
    F("state_log", "Table", options="AO Case State Log", read_only=True),
], [RW(ADMIN, delete=False), RW(WORKER), RW(REVIEWER, create=False), RO(FINANCE), RO(AUDITOR),
    perm(ADMIN, read=1, write=1, permlevel=1), perm("System Manager", read=1, permlevel=0)],
    autoname="format:AC-{YYYY}-{#####}", naming_rule="Expression", title_field="customer_name",
    search_fields="customer_name,program,case_state"))

D.append(doctype("AO Case Message", [
    F("case", "Link", options="AO Application Case", reqd=True, in_list_view=True, set_only_once=True),
    F("visibility", "Select", options="Internal\nCustomer", reqd=True, in_list_view=True),
    F("direction", "Select", options="Staff\nCustomer", reqd=True, in_list_view=True),
    F("author", "Link", options="User", reqd=True, in_list_view=True),
    F("body", "Long Text", reqd=True),
], [RW(ADMIN), RW(WORKER), RW(REVIEWER), RO(AUDITOR)], autoname="format:MSG-{######}", naming_rule="Expression"))

D.append(doctype("AO Workflow Transition", [
    F("from_state", "Select", options="\n".join(STATES), reqd=True, in_list_view=True),
    F("to_state", "Select", options="\n".join(STATES), reqd=True, in_list_view=True),
    F("allowed_roles", "Data", reqd=True, in_list_view=True,
      description="Comma separated Role names. The token 'Customer' allows the case owner acting through the portal."),
    F("requires_reason", "Check"),
    F("notification_event", "Data", description="Notification template key sent to the customer on this transition (optional)"),
    F("enabled", "Check", default=True),
], [RW(ADMIN, delete=True), RO(WORKER), RO(AUDITOR)], autoname="format:WT-{#####}", naming_rule="Expression"))

# ---------------------------------------------------------------- documents
D.append(doctype("AO Document Version", [
    F("version", "Int", read_only=True, in_list_view=True),
    F("file", "Data", read_only=True, in_list_view=True),
    F("original_filename", "Data", read_only=True),
    F("sha256", "Data", read_only=True),
    F("size_bytes", "Int", read_only=True),
    F("content_type", "Data", read_only=True),
    F("uploaded_by", "Data", read_only=True),
    F("uploaded_at", "Datetime", read_only=True, in_list_view=True),
], [], istable=1))

DOC_STATUS = "Not Uploaded\nUploaded\nIn Review\nApproved\nCorrection Required"
D.append(doctype("AO Required Document", [
    F("case", "Link", options="AO Application Case", reqd=True, in_list_view=True, in_standard_filter=True, set_only_once=True),
    F("customer", "Link", options="Customer", read_only=True, fetch_from="case.customer"),
    F("document_category", "Data", reqd=True, in_list_view=True),
    F("required", "Check", default=True, in_list_view=True),
    F("upload_status", "Select", options="Not Uploaded\nUploaded", default="Not Uploaded", read_only=True, in_list_view=True),
    F("review_status", "Select", options="Pending\nIn Review\nApproved\nCorrection Required", default="Pending",
      read_only=True, in_list_view=True, in_standard_filter=True),
    COL("c1"),
    F("current_version", "Int", read_only=True),
    F("reviewer", "Link", options="User", read_only=True),
    F("review_timestamp", "Datetime", read_only=True),
    F("retention_category", "Select", options=RETENTION, default="Identity Document"),
    F("instructions", "Small Text", read_only=True),
    SEC("s_fb", "Review Outcome"),
    F("rejection_reason", "Small Text", read_only=True, description="Internal reason"),
    F("customer_feedback", "Small Text", read_only=True, description="Shown to the customer"),
    SEC("s_ver", "Versions"),
    F("versions", "Table", options="AO Document Version", read_only=True),
], [RW(ADMIN), RW(WORKER), RW(REVIEWER)], autoname="format:RD-{######}", naming_rule="Expression"))

D.append(doctype("AO Document Review", [
    F("required_document", "Link", options="AO Required Document", reqd=True, in_list_view=True, set_only_once=True),
    F("case", "Link", options="AO Application Case", reqd=True, read_only=True, fetch_from="required_document.case"),
    F("reviewer", "Link", options="User", reqd=True, read_only=True, in_list_view=True),
    F("review_date", "Datetime", reqd=True, read_only=True),
    F("decision", "Select", options="Approved\nCorrection Required", reqd=True, in_list_view=True),
    F("version_reviewed", "Int", reqd=True, read_only=True),
    F("findings", "Small Text"),
    F("requested_corrections", "Small Text"),
    F("customer_feedback", "Small Text"),
    F("review_completed", "Check", default=True),
], [RW(ADMIN, create=True), RW(REVIEWER), RO(WORKER), RO(AUDITOR)],
    autoname="format:REV-{######}", naming_rule="Expression"))

# ---------------------------------------------------------------- forms
D.append(doctype("AO Form Approval", [
    F("case", "Link", options="AO Application Case", reqd=True, in_list_view=True, in_standard_filter=True, set_only_once=True),
    F("customer", "Link", options="Customer", read_only=True, fetch_from="case.customer"),
    F("form_template", "Data", reqd=True, in_list_view=True),
    F("approval_mode", "Select", options="In-Portal Approval\nDocuSeal Signature", default="In-Portal Approval", reqd=True),
    F("submission_status", "Select", options="Pending\nSent\nViewed\nCompleted\nDeclined\nExpired\nError",
      default="Pending", in_list_view=True, read_only=True),
    F("customer_approval", "Check", read_only=True, in_list_view=True),
    F("approval_timestamp", "Datetime", read_only=True),
    F("signature_status", "Select", options="Not Applicable\nPending\nSigned\nDeclined", default="Not Applicable", read_only=True),
    SEC("s_ds", "DocuSeal"),
    F("docuseal_template_id", "Data", read_only=True),
    F("docuseal_submission_id", "Data", read_only=True, search_index=True),
    F("docuseal_submitter_id", "Data", read_only=True),
    F("docuseal_signing_url", "Data", read_only=True, hidden=True),
    F("signed_document_file", "Data", read_only=True, description="Private File containing the signed PDF"),
    F("last_error", "Small Text", read_only=True),
], [RW(ADMIN), RW(WORKER), RO(REVIEWER), RO(AUDITOR)], autoname="format:FA-{######}", naming_rule="Expression"))

# ---------------------------------------------------------------- submission
D.append(doctype("AO Official Submission", [
    F("case", "Link", options="AO Application Case", reqd=True, in_list_view=True, in_standard_filter=True, set_only_once=True),
    F("submitted_by", "Link", options="User", reqd=True, read_only=True, in_list_view=True),
    F("human_submission_attestation", "Check", reqd=True, description=
      "I personally submitted this application through the official website. It was not submitted by a bot or script, "
      "and no CAPTCHA or access restriction was bypassed."),
    F("official_portal", "Data", reqd=True, in_list_view=True, description="Name / URL of the official website used"),
    F("submission_timestamp", "Datetime", reqd=True, in_list_view=True),
    F("official_confirmation_number", "Data", reqd=True, in_list_view=True),
    F("submission_status", "Select", options="Submitted\nConfirmation Received\nFollow-up Needed\nOfficial Update Received",
      default="Submitted", reqd=True),
    F("follow_up_date", "Date"),
    F("evidence_file", "Attach", description="Receipt / screenshot (stored as a private file)"),
    F("customer_can_download_evidence", "Check", description="Allow the customer to download this receipt from the portal"),
    F("official_correspondence", "Long Text", description="Staff summary of official correspondence. Do not paste passport numbers."),
    F("customer_visible_update", "Small Text", description="Shown to the customer when staff enter an official status update"),
], [RW(ADMIN), RW(WORKER), RO(REVIEWER), RO(AUDITOR), RO(FINANCE)],
    autoname="format:OS-{######}", naming_rule="Expression"))

# ---------------------------------------------------------------- referral
D.append(doctype("AO Referral Communication", [
    F("communicated_on", "Datetime", reqd=True, in_list_view=True),
    F("direction", "Select", options="To Professional\nFrom Professional\nTo Customer", in_list_view=True),
    F("summary", "Small Text", reqd=True, in_list_view=True),
], [], istable=1))

D.append(doctype("AO Referral", [
    F("case", "Link", options="AO Application Case", reqd=True, in_list_view=True, in_standard_filter=True, set_only_once=True),
    F("reason", "Small Text", reqd=True),
    F("referral_status", "Select", options="Proposed\nContacted\nAccepted by Professional\nDeclined\nClosed",
      default="Proposed", in_list_view=True, in_standard_filter=True),
    COL("c1"),
    F("professional_or_organization", "Data", reqd=True, in_list_view=True),
    F("jurisdiction", "Data", reqd=True),
    F("customer_notified", "Check", read_only=True),
    SEC("s_lic", "Licence / Registration (verified by authorised staff only)"),
    F("licence_details", "Small Text", permlevel=1),
    F("licence_verified", "Check", permlevel=1, description=
      "Tick only after you personally verified the licence with the regulator. A referral is NOT proof of licensure."),
    F("verified_by", "Link", options="User", read_only=True, permlevel=1),
    F("verification_date", "Date", permlevel=1),
    F("verification_source", "Data", permlevel=1, description="Regulator register / URL consulted"),
    SEC("s_comm", "Communication History"),
    F("communications", "Table", options="AO Referral Communication"),
], [RW(ADMIN), RW(WORKER), RO(REVIEWER), RO(AUDITOR),
    perm(ADMIN, read=1, write=1, permlevel=1), perm(WORKER, read=1, permlevel=1), perm(AUDITOR, read=1, permlevel=1)],
    autoname="format:RF-{######}", naming_rule="Expression"))

# ---------------------------------------------------------------- notifications & audit
D.append(doctype("AO Notification Template", [
    F("event_key", "Data", reqd=True, in_list_view=True),
    F("language", "Data", default="en", reqd=True, in_list_view=True),
    F("enabled", "Check", default=True, in_list_view=True),
    F("subject", "Data", reqd=True),
    F("body", "Text Editor", reqd=True, description="Jinja. Variables: customer_name, case_reference, program_name, status_label, deadline, portal_url, message, office_name, disclaimer"),
], [RW(ADMIN, delete=True), RO(WORKER), RO(AUDITOR)], autoname="format:{event_key}-{language}", naming_rule="Expression"))

D.append(doctype("AO Notification Log", [
    F("dedupe_key", "Data", reqd=True, unique=True, in_list_view=True),
    F("event_key", "Data", in_list_view=True),
    F("case", "Link", options="AO Application Case"),
    F("customer", "Link", options="Customer"),
    F("recipient", "Data"),
    F("status", "Select", options="Queued\nSent\nError\nSkipped", in_list_view=True, default="Queued"),
    F("email_queue", "Data"),
    F("error", "Small Text"),
    F("sent_at", "Datetime"),
], [RO(ADMIN), RO(WORKER), RO(AUDITOR)], autoname="hash", naming_rule="Random"))

D.append(doctype("AO Audit Event", [
    F("event_time", "Datetime", reqd=True, in_list_view=True),
    F("actor", "Data", in_list_view=True),
    F("action", "Data", in_list_view=True),
    F("ref_doctype", "Data"),
    F("ref_name", "Data", in_list_view=True),
    F("case", "Data"),
    F("details", "Long Text"),
], [RO(ADMIN), RO(AUDITOR)], autoname="hash", naming_rule="Random", track_changes=0))

D.append(doctype("AO Integration Event", [
    F("event_key", "Data", reqd=True, unique=True, in_list_view=True, description="Idempotency key"),
    F("source", "Data", in_list_view=True),
    F("event_type", "Data", in_list_view=True),
    F("status", "Select", options="Received\nProcessed\nError\nIgnored", in_list_view=True, default="Received"),
    F("attempts", "Int"),
    F("received_at", "Datetime"),
    F("error", "Small Text"),
    F("payload_digest", "Data"),
    F("context", "Small Text", description="Non-sensitive identifiers needed to (re)process the event"),
], [RO(ADMIN), RO(AUDITOR)], autoname="hash", naming_rule="Random", track_changes=0))

# ---------------------------------------------------------------- privacy
D.append(doctype("AO Consent Record", [
    F("customer", "Link", options="Customer", reqd=True, in_list_view=True),
    F("user", "Link", options="User"),
    F("consent_type", "Select", options="Terms of Service\nPrivacy Notice\nSensitive Data Processing\nElectronic Signature\nMarketing", reqd=True, in_list_view=True),
    F("policy_version", "Data", in_list_view=True),
    F("granted", "Check", default=True, in_list_view=True),
    F("recorded_at", "Datetime", reqd=True),
    F("withdrawn_at", "Datetime"),
], [RO(ADMIN), RO(WORKER), RO(AUDITOR)], autoname="format:CN-{######}", naming_rule="Expression"))

D.append(doctype("AO Data Request", [
    F("customer", "Link", options="Customer", reqd=True, in_list_view=True),
    F("request_type", "Select", options="Access / Export\nCorrection\nErasure\nAccount Closure", reqd=True, in_list_view=True),
    F("details", "Small Text"),
    F("status", "Select", options="Open\nIn Progress\nCompleted\nRefused", default="Open", in_list_view=True),
    F("decision_note", "Small Text", description="If refused / partially fulfilled, state the legal or contractual retention reason"),
    F("received_at", "Datetime", read_only=True),
    F("completed_at", "Datetime", read_only=True),
], [RW(ADMIN), RO(WORKER), RO(AUDITOR)], autoname="format:DR-{#####}", naming_rule="Expression"))


def main():
    for d in D:
        folder = os.path.join(ROOT, snake(d["name"]))
        os.makedirs(folder, exist_ok=True)
        open(os.path.join(folder, "__init__.py"), "a").close()
        with open(os.path.join(folder, snake(d["name"]) + ".json"), "w") as fh:
            json.dump(d, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        py = os.path.join(folder, snake(d["name"]) + ".py")
        if not os.path.exists(py):
            cls = d["name"].replace(" ", "")
            base = "Document"
            open(py, "w").write(
                "import frappe\nfrom frappe.model.document import Document\n\n\n"
                f"class {cls}(Document):\n    pass\n")
    print(f"generated {len(D)} doctypes into {os.path.realpath(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
