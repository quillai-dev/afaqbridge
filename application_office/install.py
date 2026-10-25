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
    apply_branding_and_language()
    frappe.db.commit()


def after_migrate():
    create_roles()
    create_custom_fields(custom_fields(), ignore_validate=True)
    grant_erp_permissions()
    seed()
    scope_mfa()
    apply_branding_and_language()


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


DEFAULT_SENSITIVE_CONSENT = ("I consent to the processing of my identity documents and other sensitive personal data "
                             "solely for the purpose of preparing the application(s) I request.")
BRAND = "AfaqBridge"
LOGO = "/assets/application_office/images/afaqbridge-logo.svg"
ICON = "/assets/application_office/images/afaqbridge-icon.svg"
FAVICON = "/assets/application_office/images/favicon.svg"
# Values that mean "still the stock/previous default" - only these are replaced, administrator edits are kept.
_STOCK = (None, "", "Frappe", "ERPNext", "Frappe Framework", "Application Office", "Example Office (set in AO Settings)")


def _set(doctype: str, field: str, value, replace=_STOCK, single=True):
    cur = frappe.db.get_single_value(doctype, field)
    if cur in replace or (isinstance(cur, str) and cur.startswith("/assets/frappe/")):
        frappe.db.set_single_value(doctype, field, value)


def apply_branding_and_language():
    """Idempotent, non-destructive. Safe to run on an EXISTING site: it only sets branding / language settings and
    never touches cases, documents, signing records or other data."""
    # 1. languages: Arabic + English enabled, nothing else offered in the picker
    for code, name in (("ar", "العربية"), ("en", "English")):
        if frappe.db.exists("Language", code):
            frappe.db.set_value("Language", code, "enabled", 1)
        else:
            frappe.get_doc({"doctype": "Language", "language_code": code, "language_name": name, "enabled": 1}).insert(ignore_permissions=True)
    frappe.db.sql("update `tabLanguage` set enabled=0 where name not in ('ar','en')")
    # 2. default language: Arabic (users that explicitly chose English keep it)
    if frappe.db.get_single_value("System Settings", "language") in (None, "", "en"):
        frappe.db.set_single_value("System Settings", "language", "ar")
    # 3. branding (stock values only)
    _set("System Settings", "app_name", BRAND)
    _set("Website Settings", "app_name", BRAND)
    _set("Website Settings", "title_prefix", BRAND)
    _set("Website Settings", "app_logo", LOGO)
    _set("Website Settings", "splash_image", ICON)
    _set("Website Settings", "favicon", FAVICON)
    _set("Website Settings", "footer_logo", LOGO)
    _set("Navbar Settings", "app_logo", ICON)
    _ensure_language_menu_items()
    frappe.db.set_single_value("Website Settings", "show_language_picker", 1)  # Frappe's own picker on login/web pages
    # 4. office name shown in e-mails / portal
    if frappe.db.get_single_value("AO Settings", "office_name") in _STOCK:
        frappe.db.set_single_value("AO Settings", "office_name", BRAND)
    frappe.clear_cache()


def _ensure_language_menu_items():
    """AR / EN entries in the desk user menu via Frappe's official Navbar Settings (no DOM patching)."""
    ns = frappe.get_doc("Navbar Settings")
    have = {i.item_label for i in ns.settings_dropdown}
    changed = False
    for label, code in (("العربية", "ar"), ("English", "en")):
        if label not in have:
            ns.append("settings_dropdown", {"item_label": label, "item_type": "Action",
                                            "action": f"application_office.switch_language('{code}')", "is_standard": 0})
            changed = True
    if changed:
        ns.flags.ignore_mandatory = True
        ns.save(ignore_permissions=True)


def custom_fields():
    return {
        "Customer": [
            {"fieldname": "ao_section", "fieldtype": "Section Break", "label": "AfaqBridge", "insert_after": "language"},
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
        s.office_name, changed = "AfaqBridge", True
    if not s.disclaimer_text:
        s.disclaimer_text, changed = DEFAULT_DISCLAIMER, True
    if not s.sensitive_data_consent_text:
        s.sensitive_data_consent_text, changed = (
            DEFAULT_SENSITIVE_CONSENT, True)
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
