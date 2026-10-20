"""Customer registration/invitation. ERPNext `Customer` is the single authoritative customer record;
the portal login is a Website User linked through the Customer's `portal_users` child table."""
from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime, validate_email_address

from application_office import audit
from application_office.common import CUSTOMER_ROLE, settings

REQUIRED_CONSENTS = ("Terms of Service", "Privacy Notice", "Sensitive Data Processing")


def record_consent(customer: str, user: str | None, consent_type: str, version: str, granted: bool = True):
    return frappe.get_doc({"doctype": "AO Consent Record", "customer": customer, "user": user,
                           "consent_type": consent_type, "policy_version": version, "granted": 1 if granted else 0,
                           "recorded_at": now_datetime()}).insert(ignore_permissions=True)


def has_required_consents(customer: str) -> bool:
    """True when the customer holds a granted, un-withdrawn consent for the CURRENT policy versions."""
    s = settings()
    versions = {"Terms of Service": s.terms_version, "Privacy Notice": s.privacy_version,
                "Sensitive Data Processing": s.terms_version}
    for ctype, ver in versions.items():
        if not frappe.db.exists("AO Consent Record", {"customer": customer, "consent_type": ctype, "granted": 1,
                                                      "policy_version": ver, "withdrawn_at": ["is", "not set"]}):
            return False
    return True


def accept_consents(customer: str, user: str):
    s = settings()
    for ctype, ver in (("Terms of Service", s.terms_version), ("Privacy Notice", s.privacy_version),
                       ("Sensitive Data Processing", s.terms_version)):
        record_consent(customer, user, ctype, ver)
    frappe.db.set_value("Customer", customer, "ao_account_status", "Active")
    audit.log("customer.consent_accepted", "Customer", customer, None, {}, actor=user)


def create_customer_with_user(email: str, full_name: str, language: str | None = "en", consents: dict | None = None,
                              invited_by: str | None = None, send_welcome: bool = True) -> dict:
    """Create User + Customer + consent records. Idempotent and enumeration-safe:
    an existing e-mail returns created=False without revealing anything else."""
    email = (email or "").strip().lower()
    full_name = (full_name or "").strip()
    if not validate_email_address(email, throw=False) or not (2 <= len(full_name) <= 140):
        frappe.throw(_("Please enter a valid name and e-mail address"), frappe.ValidationError)
    consents = consents or {}
    missing = [c for c in REQUIRED_CONSENTS if not consents.get(c)]
    if missing and not invited_by:
        frappe.throw(_("You must accept: {0}").format(", ".join(missing)), frappe.ValidationError)
    if frappe.db.exists("User", email):
        return {"created": False}

    s = settings()
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": full_name[:140],
                           "enabled": 1, "user_type": "Website User", "send_welcome_email": 0,
                           "roles": [{"role": CUSTOMER_ROLE}]})
    user.flags.ignore_permissions = True
    user.insert(ignore_permissions=True)
    set_password_url = None
    if send_welcome:
        # Frappe's own welcome mail is sent immediately AFTER COMMIT, so a mail outage would turn a successful
        # registration into a 500. Generate the link ourselves and deliver it through the queued notification path.
        set_password_url = user._reset_password(send_email=False)  # v16 API; returns the one-time link
    customer = frappe.get_doc({
        "doctype": "Customer", "customer_name": full_name, "customer_type": "Individual",
        "customer_group": "Individual", "territory": "All Territories", "language": language or "en",
        "ao_customer_reference": "CU-" + frappe.generate_hash(length=8).upper(),
        "ao_account_status": "Active" if not invited_by else "Invited", "portal_users": [{"user": email}]})
    customer.insert(ignore_permissions=True)
    versions = {"Terms of Service": s.terms_version, "Privacy Notice": s.privacy_version,
                "Sensitive Data Processing": s.terms_version}
    for ctype in REQUIRED_CONSENTS:
        if consents.get(ctype):
            record_consent(customer.name, email, ctype, versions[ctype])
    if consents.get("Marketing"):
        record_consent(customer.name, email, "Marketing", s.privacy_version)
    audit.log("customer.registered", "Customer", customer.name, None,
              {"invited_by": invited_by, "language": language}, actor=invited_by or email)
    from application_office.notifications import send
    send("registration_success", customer.name, f"reg:{customer.name}",
         context={"set_password_url": set_password_url or ""})
    return {"created": True, "customer": customer.name}
