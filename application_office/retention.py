"""Retention, deletion and data-rights handling.

Nothing is deleted automatically: the daily job only flags cases whose retention period elapsed
and creates a ToDo; an administrator then runs `execute_deletion`. Backups are NOT rewritten:
data deleted here may remain in backups until the backup retention window expires."""
from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, add_years, getdate, now_datetime, today

from application_office import audit
from application_office.common import ADMIN, require_staff, settings

TERMINAL = ("CLOSED",)


def years_for(category: str) -> int:
    s = settings()
    for r in s.retention_rules:
        if r.retention_category == category:
            return int(r.years)
    return int(s.default_retention_years)


def compute_retention_until(case):
    cats = set(frappe.get_all("AO Required Document", filters={"case": case.name},
                              pluck="retention_category")) | {"Form / Approval", "Submission Evidence"}
    years = max(years_for(c) for c in cats)
    return add_years(getdate(case.closure_date or today()), years)


def flag_eligible_cases():
    """Daily: mark closed cases whose retention elapsed. Never deletes."""
    rows = frappe.get_all("AO Application Case", filters={
        "case_state": "CLOSED", "retention_until": ["<", today()], "legal_hold": 0,
        "deletion_status": ["in", ["", None]]}, pluck="name", limit=500)
    for name in rows:
        frappe.db.set_value("AO Application Case", name, "deletion_status", "Eligible")
        audit.log("retention.eligible", "AO Application Case", name, name)
        admins = frappe.get_all("Has Role", filters={"role": ADMIN, "parenttype": "User"}, pluck="parent")
        if admins:
            frappe.get_doc({"doctype": "ToDo", "allocated_to": admins[0], "reference_type": "AO Application Case",
                            "reference_name": name,
                            "description": f"Case {name} passed its retention period and may be deleted."}
                           ).insert(ignore_permissions=True)
    return rows


def execute_deletion(case_name: str, override_reason: str | None = None) -> dict:
    """Admin-only. Deletes personal data of a case (files, intake, notes, messages) but keeps a minimal
    skeleton (reference, program, dates, state log, audit trail)."""
    require_staff(ADMIN)
    case = frappe.get_doc("AO Application Case", case_name, for_update=True)
    if case.legal_hold:
        frappe.throw(_("Case is under legal hold"))
    if case.deletion_status != "Eligible":
        if case.case_state != "CLOSED" or not override_reason:
            frappe.throw(_("Case is not eligible for deletion. Only closed cases with an elapsed retention period "
                           "(or a documented override reason) may be deleted"))
        if getdate(case.retention_until or today()) > getdate(today()) and not override_reason:
            frappe.throw(_("Retention period has not elapsed"))
    removed_files = 0
    for dt in ("AO Required Document", "AO Form Approval", "AO Official Submission"):
        for name in frappe.get_all(dt, filters={"case": case.name}, pluck="name"):
            for f in frappe.get_all("File", filters={"attached_to_doctype": dt, "attached_to_name": name}, pluck="name"):
                frappe.delete_doc("File", f, ignore_permissions=True, force=True)
                removed_files += 1
    for name in frappe.get_all("AO Required Document", filters={"case": case.name}, pluck="name"):
        frappe.db.delete("AO Document Version", {"parent": name})
        frappe.db.set_value("AO Required Document", name, {
            "upload_status": "Not Uploaded", "customer_feedback": None, "rejection_reason": None})
    for dt in ("AO Case Message", "AO Document Review"):
        frappe.db.delete(dt, {"case": case.name})
    frappe.db.set_value("AO Form Approval", {"case": case.name},
                        {"docuseal_signing_url": None, "signed_document_file": None, "last_error": None})
    frappe.db.set_value("AO Official Submission", {"case": case.name},
                        {"evidence_file": None, "official_correspondence": None, "customer_visible_update": None})
    case.intake_data = None
    case.internal_notes = case.customer_visible_notes = None
    case.deletion_status = "Deleted"
    case.flags.ao_transition = True
    case.save(ignore_permissions=True)
    audit.log("retention.deleted", "AO Application Case", case.name, case.name,
              {"files_removed": removed_files, "override_reason": override_reason})
    return {"case": case.name, "files_removed": removed_files}


def customer_blockers(customer: str) -> list[str]:
    out = []
    for c in frappe.get_all("AO Application Case", filters={"customer": customer, "deletion_status": ["!=", "Deleted"]},
                            fields=["name", "case_state", "legal_hold"]):
        out.append(f"{c.name} ({'legal hold' if c.legal_hold else c.case_state})")
    return out


def execute_erasure(customer: str, request_name: str | None = None) -> dict:
    """Admin-only: close the account and anonymise the Customer when no case still needs retaining.
    ERPNext financial documents are untouched (statutory bookkeeping retention)."""
    require_staff(ADMIN)
    blockers = customer_blockers(customer)
    if blockers:
        return {"erased": False, "blockers": blockers}
    users = frappe.get_all("Portal User", filters={"parent": customer, "parenttype": "Customer"}, pluck="user")
    for u in users:
        frappe.db.delete("Sessions", {"user": u})
        frappe.db.delete("Portal User", {"parent": customer, "user": u})
        frappe.db.set_value("User", u, {"enabled": 0, "first_name": "Deleted", "last_name": "User",
                                        "mobile_no": None, "phone": None})
        # The e-mail address is the User primary key: rename it so the personal address is released.
        from frappe.model.rename_doc import rename_doc
        caller = frappe.session.user
        frappe.set_user("Administrator")  # the caller was authorised above; renaming touches system doctypes
        try:
            rename_doc("User", u, f"deleted-{frappe.generate_hash(length=10)}@erased.invalid",
                       force=True, ignore_permissions=True)
        finally:
            frappe.set_user(caller)
    ref = frappe.db.get_value("Customer", customer, "ao_customer_reference") or f"CU-{frappe.generate_hash(length=8).upper()}"
    frappe.db.set_value("Customer", customer, {"customer_name": f"Deleted customer {ref}", "disabled": 1,
                                               "ao_account_status": "Closed", "email_id": None, "mobile_no": None})
    if customer != ref:
        # ERPNext names Customers after the person by default: release the personal name from the primary key.
        from frappe.model.rename_doc import rename_doc
        caller = frappe.session.user
        frappe.set_user("Administrator")
        try:
            rename_doc("Customer", customer, ref, force=True, ignore_permissions=True)
        finally:
            frappe.set_user(caller)
        customer = ref
    if request_name:
        frappe.db.set_value("AO Data Request", request_name, {"status": "Completed", "completed_at": now_datetime()})
    audit.log("customer.erased", "Customer", customer, None, {"users_disabled": len(users)})
    return {"erased": True, "blockers": []}
