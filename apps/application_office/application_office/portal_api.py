"""Customer portal API. EVERY function derives the customer from the session and verifies ownership of
every object it touches. Responses are explicit projections: internal notes, reviewer identities and
internal rejection reasons are never included."""
from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_datetime, now_datetime, strip_html

from application_office import audit, customers, intake, uploads
from application_office.common import (
    customer_email, get_customer_case, require_customer, settings, user_rate_limit,
)
from application_office.scheduler import format_deadline
from application_office.workflow import CUSTOMER_STATUS_LABELS, compute_case_hash, transition_case

CUSTOMER_EDITABLE_STATES = ("NEW", "WAITING_FOR_DOCUMENTS", "CORRECTION_REQUIRED")
MAX_OPEN_CASES = 10
MAX_MESSAGE_LEN = 5000


def _require_consent(customer: str):
    if not customers.has_required_consents(customer):
        frappe.throw(_("Please accept the current terms, privacy notice and sensitive-data consent first"),
                     frappe.PermissionError)


# ---------------------------------------------------------------- public
@frappe.whitelist(methods=["GET"])
def csrf_token() -> str:
    """CSRF token of the signed-in session (same-origin fetch only; the portal sends it back as a header)."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required"), frappe.PermissionError)
    return frappe.sessions.get_csrf_token()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def bootstrap() -> dict:
    s = settings()
    out = {"office_name": s.office_name, "disclaimer": strip_html(s.disclaimer_text or ""),
           "terms_url": s.terms_url, "privacy_url": s.privacy_url,
           "terms_version": s.terms_version, "privacy_version": s.privacy_version,
           "sensitive_consent_text": s.sensitive_data_consent_text, "user": None}
    cust = customers_for_session()
    if cust:
        out["user"] = {"email": frappe.session.user, "customer": cust,
                       "name": frappe.db.get_value("Customer", cust, "customer_name"),
                       "consents_ok": customers.has_required_consents(cust)}
    return out


def customers_for_session():
    from application_office.common import customer_for_user
    return customer_for_user()


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=3600)
def register(email: str, full_name: str, language: str = "en", accept_terms: int = 0, accept_privacy: int = 0,
             accept_sensitive: int = 0, accept_marketing: int = 0) -> dict:
    consents = {"Terms of Service": cint(accept_terms), "Privacy Notice": cint(accept_privacy),
                "Sensitive Data Processing": cint(accept_sensitive), "Marketing": cint(accept_marketing)}
    customers.create_customer_with_user(email, full_name, (language or "en")[:10], consents)
    frappe.clear_messages()  # Frappe may queue msgprints for new users only; responses must be identical either way
    # Same response whether or not the address was already registered (prevents account enumeration).
    return {"ok": True, "message": _("If the address can be registered, a message with a link to set your password "
                                     "has been sent.")}


# ---------------------------------------------------------------- consent
@frappe.whitelist(methods=["POST"])
def accept_current_consents() -> dict:
    customer = require_customer()
    customers.accept_consents(customer, frappe.session.user)
    return {"ok": True}


# ---------------------------------------------------------------- services
def _program_summary(p) -> dict:
    stale_days = cint(p.verification_stale_after_days) or 30
    verified_age = (frappe.utils.getdate(frappe.utils.today()) - frappe.utils.getdate(p.last_verified_on)).days \
        if p.last_verified_on else 9999
    startable, reason = True, ""
    if verified_age > stale_days:
        startable, reason = False, "Our staff are re-verifying the official information; please contact the office."
    return {"name": p.name, "program_name": p.program_name, "category": p.program_category,
            "sponsor": p.sponsoring_organization, "requirements_url": p.official_requirements_url,
            "opening": format_deadline(p.opening_datetime, p.time_zone) if p.opening_datetime else None,
            "closing": format_deadline(p.closing_datetime, p.time_zone) if p.closing_datetime else None,
            "last_verified_on": str(p.last_verified_on) if p.last_verified_on else None,
            "fee_note": p.fee_note, "fee_amount": p.fee_amount, "eligibility": strip_html(p.eligibility_information or ""),
            "documents": [{"category": d.document_category, "required": d.required} for d in p.document_requirements],
            "startable": startable, "unavailable_reason": reason}


@frappe.whitelist(methods=["GET"])
def list_services() -> list[dict]:
    require_customer()
    names = frappe.get_all("AO Program", filters={"published": 1, "service_available": 1}, pluck="name",
                           order_by="program_name asc")
    return [_program_summary(frappe.get_doc("AO Program", n)) for n in names]


# ---------------------------------------------------------------- cases
def _case_row(c) -> dict:
    prog = frappe.db.get_value("AO Program", c.program, ["program_name", "time_zone"], as_dict=True)
    return {"name": c.name, "program": c.program, "program_name": prog.program_name,
            "state": c.case_state, "status_label": CUSTOMER_STATUS_LABELS.get(c.case_state, c.case_state),
            "deadline": format_deadline(c.applicable_deadline, prog.time_zone) if c.applicable_deadline else None,
            "opening_date": str(c.opening_date)}


@frappe.whitelist(methods=["GET"])
def list_cases() -> list[dict]:
    customer = require_customer()
    rows = frappe.get_all("AO Application Case", filters={"customer": customer, "deletion_status": ["!=", "Deleted"]},
                          fields=["name", "program", "case_state", "applicable_deadline", "opening_date"],
                          order_by="creation desc")
    return [_case_row(frappe._dict(r)) for r in rows]


@frappe.whitelist(methods=["POST"])
@user_rate_limit(30, 3600)
def start_case(program: str) -> dict:
    customer = require_customer()
    _require_consent(customer)
    open_cases = frappe.db.count("AO Application Case", {"customer": customer, "case_state": ["not in", ["CLOSED", "CANCELLED"]]})
    if open_cases >= MAX_OPEN_CASES:
        frappe.throw(_("You have too many open cases; please contact the office"))
    p = frappe.db.get_value("AO Program", program, ["published", "service_available", "last_verified_on",
                                                    "verification_stale_after_days"], as_dict=True)
    if not p or not p.published or not p.service_available:
        frappe.throw(_("This service is not available"), frappe.DoesNotExistError)
    summary = _program_summary(frappe.get_doc("AO Program", program))
    if not summary["startable"]:
        frappe.throw(_(summary["unavailable_reason"]))
    case = frappe.get_doc({"doctype": "AO Application Case", "customer": customer, "program": program})
    case.insert(ignore_permissions=True)
    transition_case(case.name, "WAITING_FOR_DOCUMENTS", actor_kind="customer", notify=False)
    return {"case": case.name}


def _documents_for(case_name: str) -> list[dict]:
    rows = frappe.get_all("AO Required Document", filters={"case": case_name},
                          fields=["name", "document_category", "required", "upload_status", "review_status",
                                  "current_version", "customer_feedback", "instructions"], order_by="creation asc")
    return rows


@frappe.whitelist(methods=["GET"])
def get_case(case: str) -> dict:
    doc = get_customer_case(case)
    prog = frappe.get_doc("AO Program", doc.program)
    row = _case_row(doc)
    forms = frappe.get_all("AO Form Approval", filters={"case": doc.name},
                           fields=["name", "form_template", "approval_mode", "submission_status", "signature_status"])
    msgs = frappe.get_all("AO Case Message", filters={"case": doc.name, "visibility": "Customer"},
                          fields=["direction", "body", "creation"], order_by="creation asc")
    sub = frappe.db.get_value("AO Official Submission", {"case": doc.name},
                              ["name", "submission_timestamp", "official_confirmation_number", "official_portal",
                               "customer_can_download_evidence", "evidence_file", "customer_visible_update"], as_dict=True)
    invoices = frappe.get_all("Sales Invoice", filters={"customer": doc.customer, "ao_application_case": doc.name, "docstatus": 1},
                              fields=["name", "grand_total", "outstanding_amount", "currency", "status", "due_date"])
    editable = doc.case_state in CUSTOMER_EDITABLE_STATES
    row.update({
        "customer_visible_notes": strip_html(doc.customer_visible_notes or ""),
        "documents": _documents_for(doc.name),
        "intake": intake.read(doc, reveal=True, program=prog),   # the customer's own data
        "intake_completed": bool(doc.intake_completed),
        "forms": forms,
        "messages": msgs,
        "approval_status": doc.final_customer_approval_status,
        "can_approve": doc.case_state == "READY_FOR_CUSTOMER_APPROVAL",
        "can_edit": editable,
        "can_submit_to_office": editable,
        "submission": ({"submitted_on": str(sub.submission_timestamp), "confirmation": sub.official_confirmation_number,
                        "portal": sub.official_portal, "receipt_available": bool(sub.customer_can_download_evidence and sub.evidence_file),
                        "update": sub.customer_visible_update} if sub else None),
        "invoices": invoices,
        "disclaimer": strip_html(settings().disclaimer_text or ""),
    })
    return row


@frappe.whitelist(methods=["POST"])
def save_intake(case: str, values: str, complete: int = 0) -> dict:
    doc = get_customer_case(case, for_update=True)
    _require_consent(doc.customer)
    if doc.case_state not in CUSTOMER_EDITABLE_STATES:
        frappe.throw(_("This case can no longer be edited"))
    try:
        parsed = json.loads(values)
        assert isinstance(parsed, dict)
    except Exception:
        frappe.throw(_("Invalid form data"))
    intake.store(doc, parsed, complete=bool(cint(complete)))
    doc.flags.ao_internal = True
    doc.save(ignore_permissions=True)
    audit.log("intake.saved", doc.doctype, doc.name, doc.name, {"complete": bool(cint(complete)),
                                                                "fields": sorted(parsed)})
    return {"ok": True, "intake_completed": bool(doc.intake_completed)}


def _file_from_request():
    req = getattr(frappe.local, "request", None)
    f = req.files.get("file") if req is not None else None
    if not f:
        frappe.throw(_("No file was provided"), uploads.UploadRejected)
    limit = int(settings().max_upload_mb) * 1024 * 1024
    content = f.stream.read(limit + 1)
    return f.filename or "", content


@frappe.whitelist(methods=["POST"])
@user_rate_limit(60, 3600)
def upload_document(case: str, required_document: str) -> dict:
    doc = get_customer_case(case)
    _require_consent(doc.customer)
    if doc.case_state not in CUSTOMER_EDITABLE_STATES:
        frappe.throw(_("Documents can't be uploaded in the current status"))
    rd = frappe.get_doc("AO Required Document", required_document)
    if rd.case != doc.name:
        frappe.throw(_("Document not found"), frappe.DoesNotExistError)
    if rd.review_status == "Approved":
        frappe.throw(_("This document was already approved and cannot be replaced; contact the office"))
    filename, content = _file_from_request()
    uploads.store_version(rd, filename, content, uploaded_by=frappe.session.user)
    audit.log("document.uploaded", rd.doctype, rd.name, doc.name,
              {"version": rd.current_version, "size": len(content), "category": rd.document_category})
    return {"ok": True, "version": rd.current_version}


@frappe.whitelist(methods=["POST"])
def submit_to_office(case: str) -> dict:
    doc = get_customer_case(case, for_update=True)
    _require_consent(doc.customer)
    if doc.case_state not in CUSTOMER_EDITABLE_STATES:
        frappe.throw(_("This case has already been submitted to our office for review"))
    if doc.case_state == "NEW":
        transition_case(doc.name, "WAITING_FOR_DOCUMENTS", actor_kind="customer", notify=False)
    if not doc.intake_completed:
        frappe.throw(_("Please complete the information form first"))
    missing = [d["document_category"] for d in _documents_for(doc.name)
               if d["required"] and d["upload_status"] != "Uploaded"]
    if missing:
        frappe.throw(_("Missing required documents: {0}").format(", ".join(missing)))
    needs_fix = [d["document_category"] for d in _documents_for(doc.name) if d["review_status"] == "Correction Required"]
    if needs_fix:
        frappe.throw(_("Please upload corrected versions of: {0}").format(", ".join(needs_fix)))
    transition_case(doc.name, "UNDER_REVIEW", actor_kind="customer", notify=False)
    audit.log("case.submitted_to_office", doc.doctype, doc.name, doc.name)
    return {"ok": True}


def _stream(file_name: str, filename: str):
    f = frappe.get_doc("File", file_name)
    frappe.local.response.filename = filename
    frappe.local.response.filecontent = f.get_content()
    frappe.local.response.type = "download"


@frappe.whitelist(methods=["GET"])
def download_document(case: str, required_document: str, version: int | None = None):
    doc = get_customer_case(case)
    rd = frappe.get_doc("AO Required Document", required_document)
    if rd.case != doc.name:
        frappe.throw(_("Document not found"), frappe.DoesNotExistError)
    row = next((v for v in rd.versions if (cint(version) or rd.current_version) == v.version), None)
    if not row:
        frappe.throw(_("Document not found"), frappe.DoesNotExistError)
    audit.log("document.downloaded", rd.doctype, rd.name, doc.name, {"version": row.version})
    _stream(row.file, frappe.db.get_value("File", row.file, "file_name"))


@frappe.whitelist(methods=["GET"])
def download_receipt(case: str):
    doc = get_customer_case(case)
    sub = frappe.db.get_value("AO Official Submission", {"case": doc.name},
                              ["evidence_file", "customer_can_download_evidence"], as_dict=True)
    if not sub or not sub.customer_can_download_evidence or not sub.evidence_file:
        frappe.throw(_("No receipt is available for download"), frappe.DoesNotExistError)
    fname = frappe.db.get_value("File", {"file_url": sub.evidence_file}, "name")
    if not fname:
        frappe.throw(_("No receipt is available for download"), frappe.DoesNotExistError)
    audit.log("receipt.downloaded", "AO Application Case", doc.name, doc.name)
    _stream(fname, f"receipt-{doc.name}{'.' + sub.evidence_file.rsplit('.', 1)[-1] if '.' in sub.evidence_file else ''}")


# ---------------------------------------------------------------- approval
def maybe_advance_after_approval(case_name: str):
    """READY_FOR_CUSTOMER_APPROVAL -> READY_FOR_SUBMISSION once approval AND any signatures are complete."""
    case = frappe.get_doc("AO Application Case", case_name)
    if case.case_state != "READY_FOR_CUSTOMER_APPROVAL" or case.final_customer_approval_status != "Approved":
        return False
    pending = frappe.get_all("AO Form Approval", filters={"case": case_name, "approval_mode": "DocuSeal Signature",
                                                          "signature_status": ["!=", "Signed"]}, limit=1)
    if pending:
        return False
    transition_case(case_name, "READY_FOR_SUBMISSION", actor_kind="system", notify=False)
    return True


@frappe.whitelist(methods=["POST"])
def approve_case(case: str, statement_accepted: int = 0) -> dict:
    doc = get_customer_case(case, for_update=True)
    if doc.case_state != "READY_FOR_CUSTOMER_APPROVAL":
        frappe.throw(_("This case is not waiting for your approval"))
    if not cint(statement_accepted):
        frappe.throw(_("Please confirm that the information is correct and complete"))
    doc.flags.ao_internal = True
    doc.final_customer_approval_status = "Approved"
    doc.approved_by_user = frappe.session.user
    doc.approved_on = now_datetime()
    doc.approved_data_hash = compute_case_hash(doc)
    doc.save(ignore_permissions=True)
    for fa in frappe.get_all("AO Form Approval", filters={"case": doc.name, "approval_mode": "In-Portal Approval"}, pluck="name"):
        frappe.db.set_value("AO Form Approval", fa, {"customer_approval": 1, "approval_timestamp": now_datetime(),
                                                     "submission_status": "Completed"})
    audit.log("case.customer_approved", doc.doctype, doc.name, doc.name, {"hash": doc.approved_data_hash[:12]})
    advanced = maybe_advance_after_approval(doc.name)
    return {"ok": True, "advanced": advanced}


@frappe.whitelist(methods=["POST"])
def request_changes(case: str, message: str) -> dict:
    doc = get_customer_case(case)
    message = (message or "").strip()[:MAX_MESSAGE_LEN]
    if not message:
        frappe.throw(_("Please describe the changes you need"))
    if doc.case_state != "READY_FOR_CUSTOMER_APPROVAL":
        frappe.throw(_("This case is not waiting for your approval"))
    transition_case(doc.name, "CORRECTION_REQUIRED", reason=message, actor_kind="customer", notify=False)
    frappe.get_doc({"doctype": "AO Case Message", "case": doc.name, "visibility": "Customer", "direction": "Customer",
                    "author": frappe.session.user, "body": message}).insert(ignore_permissions=True)
    _alert_staff(doc, "Customer requested changes before approving")
    return {"ok": True}


# ---------------------------------------------------------------- messages / invoices / privacy
def _alert_staff(case_doc, text: str):
    target = case_doc.assigned_employee
    if not target:
        admins = frappe.get_all("Has Role", filters={"role": "AO Administrator", "parenttype": "User"}, pluck="parent")
        target = admins[0] if admins else None
    if target:
        frappe.get_doc({"doctype": "ToDo", "allocated_to": target, "reference_type": "AO Application Case",
                        "reference_name": case_doc.name, "description": f"{text} ({case_doc.name})"}
                       ).insert(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
@user_rate_limit(30, 3600)
def send_message(case: str, body: str) -> dict:
    doc = get_customer_case(case)
    body = (body or "").strip()
    if not body or len(body) > MAX_MESSAGE_LEN:
        frappe.throw(_("Message must be between 1 and {0} characters").format(MAX_MESSAGE_LEN))
    frappe.get_doc({"doctype": "AO Case Message", "case": doc.name, "visibility": "Customer", "direction": "Customer",
                    "author": frappe.session.user, "body": body}).insert(ignore_permissions=True)
    _alert_staff(doc, "New customer message")
    return {"ok": True}


@frappe.whitelist(methods=["GET"])
def list_invoices() -> list[dict]:
    customer = require_customer()
    return frappe.get_all("Sales Invoice", filters={"customer": customer, "docstatus": 1},
                          fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount", "currency",
                                  "status", "ao_application_case as case"], order_by="posting_date desc")


@frappe.whitelist(methods=["POST"])
@user_rate_limit(10, 86400)
def data_request(request_type: str, details: str = "") -> dict:
    customer = require_customer()
    if request_type not in ("Access / Export", "Correction", "Erasure", "Account Closure"):
        frappe.throw(_("Unknown request type"))
    dr = frappe.get_doc({"doctype": "AO Data Request", "customer": customer, "request_type": request_type,
                         "details": (details or "")[:2000]}).insert(ignore_permissions=True)
    audit.log("privacy.request", dr.doctype, dr.name, None, {"type": request_type})
    return {"ok": True, "request": dr.name}


@frappe.whitelist(methods=["POST"])
@user_rate_limit(20, 3600)
def get_signing_url(case: str, form_approval: str) -> dict:
    doc = get_customer_case(case)
    fa = frappe.get_doc("AO Form Approval", form_approval)
    if fa.case != doc.name or fa.approval_mode != "DocuSeal Signature":
        frappe.throw(_("Form not found"), frappe.DoesNotExistError)
    if doc.case_state != "READY_FOR_CUSTOMER_APPROVAL":
        frappe.throw(_("Signing is not available yet"))
    from application_office.integrations.docuseal import create_signing_request
    return {"url": create_signing_request(fa.name)}
