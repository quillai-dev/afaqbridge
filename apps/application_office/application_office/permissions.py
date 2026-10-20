"""Row-level permissions.

* Website (portal) users have NO desk permissions on any AO doctype; the portal uses vetted whitelisted
  methods only. These hooks additionally deny direct REST / desk access for them (defence in depth).
* Case workers only see cases assigned to them or still unassigned. Reviewers, finance, auditors and
  administrators see all cases (their doctype permissions still limit what they can do)."""
from __future__ import annotations

import frappe

from application_office.common import GLOBAL_READ_ROLES, STAFF_ROLES, WORKER, is_global_reader

CASE_CHILD = {"AO Required Document", "AO Document Review", "AO Form Approval", "AO Official Submission",
              "AO Referral", "AO Case Message"}


def _is_portal_user(user: str) -> bool:
    return user != "Administrator" and not (STAFF_ROLES & set(frappe.get_roles(user)))


def _case_filter(user: str, case_col: str) -> str:
    esc = frappe.db.escape(user)
    return (f"{case_col} in (select `name` from `tabAO Application Case` "
            f"where ifnull(`assigned_employee`, '') in ('', {esc}))")


def case_query(user: str | None = None) -> str:
    user = user or frappe.session.user
    if _is_portal_user(user):
        return "1=0"
    if is_global_reader(user):
        return ""
    return f"ifnull(`tabAO Application Case`.`assigned_employee`, '') in ('', {frappe.db.escape(user)})"


def child_query(doctype: str):
    def inner(user: str | None = None) -> str:
        user = user or frappe.session.user
        if _is_portal_user(user):
            return "1=0"
        if is_global_reader(user):
            return ""
        return _case_filter(user, f"`tab{doctype}`.`case`")
    return inner


required_document_query = child_query("AO Required Document")
document_review_query = lambda user=None: (  # noqa: E731
    "1=0" if _is_portal_user(user or frappe.session.user) else ""
    if is_global_reader(user) else
    f"`tabAO Document Review`.`required_document` in (select `name` from `tabAO Required Document` where "
    f"{_case_filter(user or frappe.session.user, '`case`')})")
form_approval_query = child_query("AO Form Approval")
official_submission_query = child_query("AO Official Submission")
referral_query = child_query("AO Referral")
case_message_query = child_query("AO Case Message")


def _portal_denied(user: str) -> bool:
    return _is_portal_user(user)


def case_has_permission(doc, user=None, ptype=None, debug=False):
    user = user or frappe.session.user
    if _portal_denied(user):
        return False
    if is_global_reader(user):
        return True
    if WORKER in frappe.get_roles(user) and (doc.get("assigned_employee") or user) != user:
        return False
    return True


def child_has_permission(doc, user=None, ptype=None, debug=False):
    user = user or frappe.session.user
    if _portal_denied(user):
        return False
    case = doc.get("case")
    if not case and doc.get("required_document"):
        case = frappe.db.get_value("AO Required Document", doc.required_document, "case")
    if is_global_reader(user) or not case:
        return True
    assigned = frappe.db.get_value("AO Application Case", case, "assigned_employee")
    if assigned and assigned != user:
        return False
    return True


def deny_portal(doc, user=None, ptype=None, debug=False):
    return False if _portal_denied(user or frappe.session.user) else True
