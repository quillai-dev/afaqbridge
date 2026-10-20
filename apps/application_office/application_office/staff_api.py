"""Employee workspace API. Every method re-checks roles AND row-level permission on the case."""
from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from application_office import audit, intake, retention
from application_office.common import ADMIN, FINANCE, REVIEWER, WORKER, require_staff
from application_office.workflow import available_transitions, compute_case_hash, transition_case, required_documents

MAX_TEXT = 5000


def _case(name: str, ptype: str = "read"):
    doc = frappe.get_doc("AO Application Case", name)
    if not frappe.has_permission("AO Application Case", ptype, doc=doc):
        frappe.throw(_("You are not permitted to access this case"), frappe.PermissionError)
    return doc


@frappe.whitelist(methods=["GET"])
def case_actions(case: str) -> dict:
    require_staff()
    doc = _case(case)
    return {"state": doc.case_state, "transitions": available_transitions(doc, "staff")}


@frappe.whitelist(methods=["POST"])
def transition(case: str, to_state: str, reason: str = "") -> dict:
    require_staff(WORKER, REVIEWER, ADMIN)
    _case(case, "write")
    doc = transition_case(case, to_state, reason=(reason or "")[:MAX_TEXT], actor_kind="staff")
    return {"state": doc.case_state}


@frappe.whitelist(methods=["POST"])
def review_document(required_document: str, decision: str, findings: str = "", requested_corrections: str = "",
                    customer_feedback: str = "") -> dict:
    require_staff(REVIEWER, ADMIN)
    rd = frappe.get_doc("AO Required Document", required_document)
    _case(rd.case, "write")
    r = frappe.get_doc({"doctype": "AO Document Review", "required_document": required_document, "decision": decision,
                        "findings": findings[:MAX_TEXT], "requested_corrections": requested_corrections[:MAX_TEXT],
                        "customer_feedback": customer_feedback[:MAX_TEXT]})
    r.insert()
    return {"review": r.name, "version_reviewed": r.version_reviewed}


@frappe.whitelist(methods=["POST"])
def add_message(case: str, body: str, visibility: str = "Internal") -> dict:
    require_staff(WORKER, REVIEWER, ADMIN)
    _case(case, "write")
    if visibility not in ("Internal", "Customer") or not (body or "").strip():
        frappe.throw(_("Invalid message"))
    m = frappe.get_doc({"doctype": "AO Case Message", "case": case, "visibility": visibility, "direction": "Staff",
                        "author": frappe.session.user, "body": body[:MAX_TEXT]}).insert()
    return {"message": m.name}


@frappe.whitelist(methods=["GET"])
def final_checklist(case: str) -> list[dict]:
    require_staff()
    doc = _case(case)
    prog = frappe.get_doc("AO Program", doc.program)
    docs = required_documents(doc.name)
    stale = (getdate(today()) - getdate(prog.last_verified_on)).days if prog.last_verified_on else 9999
    sigs = frappe.get_all("AO Form Approval", filters={"case": case, "approval_mode": "DocuSeal Signature",
                                                       "signature_status": ["!=", "Signed"]}, limit=1)
    checks = [
        ("Intake form completed", bool(doc.intake_completed)),
        ("All required documents approved", all(d.review_status == "Approved" for d in docs if d.required)),
        ("Program information verified recently", stale <= (prog.verification_stale_after_days or 30)),
        ("Customer approval recorded", doc.final_customer_approval_status == "Approved" or not doc.customer_approval_required),
        ("Approved data unchanged since approval", (not doc.customer_approval_required) or doc.approved_data_hash == compute_case_hash(doc)),
        ("Required signatures complete", not sigs),
    ]
    return [{"check": c, "ok": ok} for c, ok in checks]


@frappe.whitelist(methods=["POST"])
def reveal_intake(case: str) -> list[dict]:
    require_staff(WORKER, REVIEWER, ADMIN)
    doc = _case(case, "read")
    audit.log("intake.revealed", doc.doctype, doc.name, doc.name)
    return intake.read(doc, reveal=True)


@frappe.whitelist(methods=["GET"])
def masked_intake(case: str) -> list[dict]:
    require_staff()
    return intake.read(_case(case))


@frappe.whitelist(methods=["POST"])
def create_invoice(case: str, items: str) -> dict:
    """Creates a DRAFT ERPNext Sales Invoice linked to the case. Currency, taxes and payment providers come
    from the ERPNext Company configuration; nothing is assumed here. Card data is never handled."""
    require_staff(FINANCE, ADMIN)
    doc = _case(case, "read")
    rows = json.loads(items)
    if not rows or not isinstance(rows, list):
        frappe.throw(_("At least one item is required"))
    inv = frappe.get_doc({"doctype": "Sales Invoice", "customer": doc.customer, "ao_application_case": doc.name,
                          "posting_date": today(), "due_date": frappe.utils.add_days(today(), 14),
                          "items": [{"item_code": "AO-SERVICE", "description": str(r["description"])[:300],
                                     "qty": float(r.get("qty", 1)), "rate": float(r["rate"])} for r in rows]})
    inv.insert()
    audit.log("invoice.created", "Sales Invoice", inv.name, doc.name)
    return {"invoice": inv.name}


@frappe.whitelist(methods=["POST"])
def delete_case_data(case: str, override_reason: str = "") -> dict:
    require_staff(ADMIN)
    return retention.execute_deletion(case, override_reason or None)


@frappe.whitelist(methods=["POST"])
def invite_customer(email: str, full_name: str, language: str = "en") -> dict:
    require_staff(WORKER, ADMIN)
    from application_office.customers import create_customer_with_user
    return create_customer_with_user(email, full_name, language, invited_by=frappe.session.user)


@frappe.whitelist(methods=["POST"])
def sync_signing_request(form_approval: str) -> dict:
    """Staff can (re)create a DocuSeal signing request, e.g. after an outage."""
    require_staff(WORKER, ADMIN)
    fa = frappe.get_doc("AO Form Approval", form_approval)
    _case(fa.case, "write")
    from application_office.integrations.docuseal import create_signing_request
    create_signing_request(form_approval)
    return {"ok": True}
