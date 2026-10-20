"""Idempotent installation: roles, custom fields on ERPNext doctypes, security hardening, seed data."""
from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from application_office.common import AO_ROLES

DEFAULT_DISCLAIMER = (
    "<p>This office provides <b>administrative assistance</b> with applications. We do <b>not</b> guarantee "
    "acceptance, selection, visa issuance or any immigration outcome, and we do <b>not</b> provide legal or "
    "immigration advice unless we are appropriately authorised to do so. Official decisions are made solely by "
    "the relevant authority or organisation. Applications are submitted on the official website by our staff, "
    "never by automated tools. [PLACEHOLDER: have this text reviewed by a qualified lawyer for every "
    "jurisdiction in which you operate.]</p>")


def after_install():
    create_roles()
    create_custom_fields(custom_fields(), ignore_validate=True)
    grant_erp_permissions()
    seed()
    configure_customer_naming()
    harden_system_settings()
    scope_mfa()
    frappe.db.commit()


def after_migrate():
    create_roles()
    create_custom_fields(custom_fields(), ignore_validate=True)
    grant_erp_permissions()
    seed()
    scope_mfa()


ERP_PERMS = {
    # doctype: {role: rights}
    "Sales Invoice": {"AO Finance": ("read", "write", "create", "submit", "cancel", "report", "export"),
                      "AO Administrator": ("read", "write", "create", "submit", "report", "export"),
                      "AO Auditor": ("read", "report", "export"), "AO Case Worker": ("read",)},
    "Payment Entry": {"AO Finance": ("read", "write", "create", "submit", "cancel", "report", "export"),
                      "AO Auditor": ("read", "report", "export")},
    "Customer": {r: ("read",) for r in AO_ROLES} | {"AO Administrator": ("read", "write", "create"),
                                                     "AO Case Worker": ("read", "write")},
    "Item": {r: ("read",) for r in AO_ROLES},
}


def grant_erp_permissions():
    """Custom DocPerms on ERPNext doctypes (no ERPNext core files are modified)."""
    from frappe.permissions import add_permission, update_permission_property
    for dt, roles in ERP_PERMS.items():
        for role, rights in roles.items():
            add_permission(dt, role, 0)
            for r in rights:
                update_permission_property(dt, role, 0, r, 1)


def create_roles():
    for r in AO_ROLES:
        if not frappe.db.exists("Role", r):
            frappe.get_doc({"doctype": "Role", "role_name": r, "desk_access": 1}).insert(ignore_permissions=True)
    scope_mfa()


def scope_mfa():
    """MFA for every employee role (Frappe scopes 2FA per Role). Enabling 2FA in System Settings also flags the
    catch-all 'All' role, which would force customers into OTP, so it is cleared. Must run AFTER hardening."""
    for r in (*AO_ROLES, "System Manager"):
        frappe.db.set_value("Role", r, "two_factor_auth", 1)
    for r in ("All", "Customer", "Guest"):
        frappe.db.set_value("Role", r, "two_factor_auth", 0)


def custom_fields():
    return {
        "Customer": [
            {"fieldname": "ao_section", "fieldtype": "Section Break", "label": "Application Office", "insert_after": "language"},
            {"fieldname": "ao_customer_reference", "fieldtype": "Data", "label": "Customer Reference", "read_only": 1,
             "unique": 1, "no_copy": 1, "insert_after": "ao_section"},
            {"fieldname": "ao_account_status", "fieldtype": "Select", "label": "Account Status",
             "options": "Active\nInvited\nSuspended\nClosed", "default": "Active", "insert_after": "ao_customer_reference"},
            {"fieldname": "ao_phone", "fieldtype": "Data", "label": "Phone (only if needed)", "options": "Phone",
             "insert_after": "ao_account_status"},
        ],
        "Sales Invoice": [
            {"fieldname": "ao_application_case", "fieldtype": "Link", "options": "AO Application Case",
             "label": "Application Case", "insert_after": "customer", "search_index": 1},
        ],
    }


def seed():
    from application_office.notifications import seed_templates
    from application_office.workflow import seed_default_transitions
    seed_default_transitions()
    seed_templates()
    s = frappe.get_doc("AO Settings")
    changed = False
    if not s.office_name:
        s.office_name, changed = "Example Office (set in AO Settings)", True
    if not s.disclaimer_text:
        s.disclaimer_text, changed = DEFAULT_DISCLAIMER, True
    if not s.sensitive_data_consent_text:
        s.sensitive_data_consent_text, changed = (
            "I consent to the processing of my identity documents and other sensitive personal data solely for "
            "the purpose of preparing the application(s) I request.", True)
    if not s.retention_rules:
        for cat, yrs in (("Identity Document", 2), ("Educational Record", 3), ("Form / Approval", 7),
                         ("Submission Evidence", 7), ("Financial", 10), ("Other", 3)):
            s.append("retention_rules", {"retention_category": cat, "years": yrs})
        changed = True
    if changed:
        s.save(ignore_permissions=True)
    if not frappe.db.exists("Item", "AO-SERVICE"):
        try:
            frappe.get_doc({"doctype": "Item", "item_code": "AO-SERVICE", "item_name": "Administrative service",
                            "item_group": "Services", "stock_uom": "Nos", "is_stock_item": 0,
                            "description": "Administrative application assistance"}).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="AO seed: could not create AO-SERVICE item (run ERPNext setup wizard first)")


def configure_customer_naming():
    # Name Customers by series, not by person name, so personal names are not primary keys.
    if frappe.db.get_single_value("Selling Settings", "cust_master_name") != "Naming Series":
        frappe.db.set_single_value("Selling Settings", "cust_master_name", "Naming Series")


def harden_system_settings():
    """Safer defaults. All are adjustable by administrators afterwards."""
    ss = frappe.get_doc("System Settings")
    ss.update({
        "enable_two_factor_auth": 1, "two_factor_method": "OTP App",
        "enable_password_policy": 1, "minimum_password_score": "3",
        "allow_consecutive_login_attempts": 5, "allow_login_after_fail": 120,
        "session_expiry": "02:00", "session_expiry_mobile": "02:00",
        "deny_multiple_sessions": 0, "force_user_to_reset_password": 0,
    })
    ss.flags.ignore_mandatory = True
    try:
        ss.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="AO install: some System Settings could not be applied")
    ws = frappe.get_doc("Website Settings")
    ws.disable_signup = 1  # self-signup through the generic /login page is off; our rate-limited API is used
    ws.flags.ignore_mandatory = True
    ws.save(ignore_permissions=True)
