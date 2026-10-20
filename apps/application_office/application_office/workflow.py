"""Configurable case workflow engine.

Valid transitions live in the `AO Workflow Transition` DocType (seeded at install, editable by
administrators). The engine enforces: transition exists, actor is allowed, reason supplied when
required, hard business guards (code), and records an immutable state log + audit event.

"SUBMITTED" only means a human recorded a completed submission. It never implies acceptance."""
from __future__ import annotations

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_years, getdate, now_datetime, today

from application_office import audit
from application_office.common import CUSTOMER_ROLE, customer_for_user

CUSTOMER_STATUS_LABELS = {
    "NEW": "Received",
    "WAITING_FOR_DOCUMENTS": "Waiting for your documents",
    "UNDER_REVIEW": "Under review by our office",
    "CORRECTION_REQUIRED": "Action needed: corrections required",
    "READY_FOR_CUSTOMER_APPROVAL": "Waiting for your approval",
    "READY_FOR_SUBMISSION": "Approved - being prepared for submission by our staff",
    "SUBMITTED": "Submitted to the official website by our staff",
    "AWAITING_OFFICIAL_UPDATE": "Submitted - awaiting official update",
    "COMPLETED": "Administrative service completed",
    "ON_HOLD": "On hold",
    "CANCELLED": "Cancelled",
    "REJECTED_BY_OFFICIAL_AUTHORITY": "Official authority did not accept the application",
    "CLOSED": "Closed",
}

# Default transitions: (from, to, roles, requires_reason, notification_event)
S, W, R, A, C = "AO Case Worker", "AO Reviewer", None, "AO Administrator", CUSTOMER_ROLE
DEFAULT_TRANSITIONS = [
    ("NEW", "WAITING_FOR_DOCUMENTS", f"{S},{A},{C}", 0, "application_received"),
    ("NEW", "ON_HOLD", f"{S},{A}", 1, None),
    ("NEW", "CANCELLED", f"{S},{A},{C}", 1, None),
    ("WAITING_FOR_DOCUMENTS", "UNDER_REVIEW", f"{S},{A},{C}", 0, None),
    ("WAITING_FOR_DOCUMENTS", "ON_HOLD", f"{S},{A}", 1, None),
    ("WAITING_FOR_DOCUMENTS", "CANCELLED", f"{S},{A},{C}", 1, None),
    ("UNDER_REVIEW", "CORRECTION_REQUIRED", f"{S},{W},{A}", 1, "correction_request"),
    ("UNDER_REVIEW", "READY_FOR_CUSTOMER_APPROVAL", f"{S},{W},{A}", 0, "approval_request"),
    ("UNDER_REVIEW", "READY_FOR_SUBMISSION", f"{S},{W},{A}", 0, None),
    ("UNDER_REVIEW", "WAITING_FOR_DOCUMENTS", f"{S},{W},{A}", 1, "missing_documents"),
    ("UNDER_REVIEW", "ON_HOLD", f"{S},{A}", 1, None),
    ("UNDER_REVIEW", "CANCELLED", f"{S},{A}", 1, None),
    ("CORRECTION_REQUIRED", "UNDER_REVIEW", f"{S},{W},{A},{C}", 0, None),
    ("CORRECTION_REQUIRED", "ON_HOLD", f"{S},{A}", 1, None),
    ("CORRECTION_REQUIRED", "CANCELLED", f"{S},{A},{C}", 1, None),
    ("READY_FOR_CUSTOMER_APPROVAL", "READY_FOR_SUBMISSION", f"{S},{A},{C}", 0, None),
    ("READY_FOR_CUSTOMER_APPROVAL", "CORRECTION_REQUIRED", f"{S},{W},{A},{C}", 1, "correction_request"),
    ("READY_FOR_CUSTOMER_APPROVAL", "UNDER_REVIEW", f"{S},{W},{A}", 1, None),
    ("READY_FOR_CUSTOMER_APPROVAL", "CANCELLED", f"{S},{A},{C}", 1, None),
    ("READY_FOR_SUBMISSION", "SUBMITTED", f"{S},{A}", 0, "submission_recorded"),
    ("READY_FOR_SUBMISSION", "UNDER_REVIEW", f"{S},{W},{A}", 1, None),
    ("READY_FOR_SUBMISSION", "ON_HOLD", f"{S},{A}", 1, None),
    ("READY_FOR_SUBMISSION", "CANCELLED", f"{S},{A},{C}", 1, None),
    ("SUBMITTED", "AWAITING_OFFICIAL_UPDATE", f"{S},{A}", 0, None),
    ("SUBMITTED", "COMPLETED", f"{S},{A}", 0, None),
    ("AWAITING_OFFICIAL_UPDATE", "COMPLETED", f"{S},{A}", 0, "official_update"),
    ("AWAITING_OFFICIAL_UPDATE", "REJECTED_BY_OFFICIAL_AUTHORITY", f"{S},{A}", 1, "official_update"),
    ("ON_HOLD", "WAITING_FOR_DOCUMENTS", f"{S},{A}", 0, None),
    ("ON_HOLD", "UNDER_REVIEW", f"{S},{A}", 0, None),
    ("ON_HOLD", "CANCELLED", f"{S},{A}", 1, None),
    ("COMPLETED", "CLOSED", f"{S},{A}", 0, "case_closed"),
    ("REJECTED_BY_OFFICIAL_AUTHORITY", "CLOSED", f"{S},{A}", 0, "case_closed"),
    ("CANCELLED", "CLOSED", f"{S},{A}", 0, "case_closed"),
]
RESET_APPROVAL_STATES = {"UNDER_REVIEW", "CORRECTION_REQUIRED", "WAITING_FOR_DOCUMENTS", "ON_HOLD"}


class TransitionError(frappe.ValidationError):
    pass


def seed_default_transitions():
    for fr, to, roles, reason, event in DEFAULT_TRANSITIONS:
        if frappe.db.exists("AO Workflow Transition", {"from_state": fr, "to_state": to}):
            continue
        frappe.get_doc({"doctype": "AO Workflow Transition", "from_state": fr, "to_state": to,
                        "allowed_roles": roles, "requires_reason": reason,
                        "notification_event": event, "enabled": 1}).insert(ignore_permissions=True)


def find_transition(from_state: str, to_state: str):
    rows = frappe.get_all("AO Workflow Transition",
                          filters={"from_state": from_state, "to_state": to_state, "enabled": 1},
                          fields=["name", "allowed_roles", "requires_reason", "notification_event"], limit=1)
    return rows[0] if rows else None


def available_transitions(case, actor_kind: str = "staff") -> list[dict]:
    rows = frappe.get_all("AO Workflow Transition", filters={"from_state": case.case_state, "enabled": 1},
                          fields=["to_state", "allowed_roles", "requires_reason"])
    out = []
    for r in rows:
        if _actor_allowed(r["allowed_roles"], actor_kind):
            out.append(r)
    return out


def _actor_allowed(allowed_roles: str, actor_kind: str) -> bool:
    allowed = {x.strip() for x in (allowed_roles or "").split(",") if x.strip()}
    if actor_kind == "system":
        return True
    if actor_kind == "customer":
        return CUSTOMER_ROLE in allowed
    roles = set(frappe.get_roles(frappe.session.user))
    return bool(roles & (allowed - {CUSTOMER_ROLE}))


# ---------------------------------------------------------------- hashing / guards
def compute_case_hash(case) -> str:
    docs = []
    for name in sorted(frappe.get_all("AO Required Document", filters={"case": case.name}, pluck="name")):
        rd = frappe.get_doc("AO Required Document", name)
        docs.append([rd.name, rd.current_version, [v.sha256 for v in rd.versions]])
    payload = json.dumps({"program": case.program, "intake": case.intake_data or "", "docs": docs}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def required_documents(case_name: str):
    return frappe.get_all("AO Required Document", filters={"case": case_name},
                          fields=["name", "document_category", "required", "upload_status", "review_status"])


def check_guards(case, to_state: str):
    if to_state == "READY_FOR_CUSTOMER_APPROVAL" or (to_state == "READY_FOR_SUBMISSION" and
                                                     case.case_state == "UNDER_REVIEW"):
        problems = [d.document_category for d in required_documents(case.name)
                    if d.required and d.review_status != "Approved"]
        if problems:
            frappe.throw(_("Required documents not approved: {0}").format(", ".join(problems)), TransitionError)
        if not case.intake_completed:
            frappe.throw(_("The intake form has not been completed"), TransitionError)
    if to_state == "READY_FOR_SUBMISSION":
        if case.customer_approval_required:
            if case.final_customer_approval_status != "Approved":
                frappe.throw(_("Customer approval is required before submission"), TransitionError)
            if case.approved_data_hash != compute_case_hash(case):
                frappe.throw(_("Case data changed after the customer approved it; request approval again"), TransitionError)
        pending_sig = frappe.get_all("AO Form Approval", filters={
            "case": case.name, "approval_mode": "DocuSeal Signature", "signature_status": ["!=", "Signed"]}, limit=1)
        if pending_sig:
            frappe.throw(_("A required signature is still outstanding"), TransitionError)
    if to_state == "SUBMITTED":
        if not frappe.db.exists("AO Official Submission", {"case": case.name}):
            frappe.throw(_("An Official Submission record entered by an employee is required"), TransitionError)


# ---------------------------------------------------------------- engine
def transition_case(case_name: str, to_state: str, reason: str | None = None, actor_kind: str = "staff",
                    notify: bool = True):
    """Move a case to a new state. actor_kind: 'staff' | 'customer' | 'system'."""
    case = frappe.get_doc("AO Application Case", case_name, for_update=True)
    if actor_kind == "customer" and case.customer != customer_for_user():
        frappe.throw(_("Case not found"), frappe.DoesNotExistError)
    frm = case.case_state
    t = find_transition(frm, to_state)
    if not t:
        frappe.throw(_("Transition {0} → {1} is not allowed").format(frm, to_state), TransitionError)
    if not _actor_allowed(t["allowed_roles"], actor_kind):
        frappe.throw(_("You are not permitted to move a case from {0} to {1}").format(frm, to_state),
                     frappe.PermissionError)
    if t["requires_reason"] and not (reason or "").strip():
        frappe.throw(_("A reason is required for this transition"), TransitionError)
    check_guards(case, to_state)

    case.flags.ao_transition = True
    case.case_state = to_state
    case.append("state_log", {"from_state": frm, "to_state": to_state, "actor": frappe.session.user,
                              "changed_at": now_datetime(), "reason": (reason or "")[:500]})
    if to_state in RESET_APPROVAL_STATES and case.final_customer_approval_status in ("Approved", "Requested"):
        case.final_customer_approval_status = "Not Requested"
        case.approved_by_user = case.approved_on = case.approved_data_hash = None
    if to_state == "READY_FOR_CUSTOMER_APPROVAL":
        case.final_customer_approval_status = "Requested"
    if to_state == "CLOSED":
        case.closure_date = today()
        from application_office.retention import compute_retention_until
        case.retention_until = compute_retention_until(case)
    case.save(ignore_permissions=True)
    audit.log("case.transition", "AO Application Case", case.name, case.name,
              {"from": frm, "to": to_state, "actor_kind": actor_kind, "reason": reason})
    if notify and t.get("notification_event"):
        from application_office.notifications import notify_case
        notify_case(t["notification_event"], case, dedupe_key=f"{case.name}:{t['notification_event']}:{len(case.state_log)}",
                    message=reason if actor_kind == "staff" and t["notification_event"] in
                    ("correction_request", "missing_documents", "official_update") else None)
    return case
