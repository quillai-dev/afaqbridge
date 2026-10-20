"""Shared helpers: roles, settings, customer resolution and ownership checks."""
from __future__ import annotations

import frappe
from frappe import _

ADMIN = "AO Administrator"
WORKER = "AO Case Worker"
REVIEWER = "AO Reviewer"
FINANCE = "AO Finance"
AUDITOR = "AO Auditor"
AO_ROLES = (ADMIN, WORKER, REVIEWER, FINANCE, AUDITOR)
# Roles that may see every case (still subject to doctype-level permissions)
GLOBAL_READ_ROLES = {ADMIN, REVIEWER, FINANCE, AUDITOR, "System Manager"}
STAFF_ROLES = set(AO_ROLES) | {"System Manager"}
CUSTOMER_ROLE = "Customer"


def settings():
    return frappe.get_cached_doc("AO Settings")


def is_staff(user: str | None = None) -> bool:
    user = user or frappe.session.user
    if user in ("Administrator",):
        return True
    return bool(STAFF_ROLES & set(frappe.get_roles(user)))


def is_global_reader(user: str | None = None) -> bool:
    user = user or frappe.session.user
    return user == "Administrator" or bool(GLOBAL_READ_ROLES & set(frappe.get_roles(user)))


def require_staff(*roles: str):
    """Server-side role gate for staff endpoints. Never rely on UI hiding."""
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Login required"), frappe.PermissionError)
    allowed = set(roles) | {"System Manager"} if roles else STAFF_ROLES
    if user != "Administrator" and not (allowed & set(frappe.get_roles(user))):
        frappe.throw(_("You are not permitted to perform this action"), frappe.PermissionError)


def customer_for_user(user: str | None = None) -> str | None:
    user = user or frappe.session.user
    if user in ("Guest", "Administrator"):
        return None
    rows = frappe.get_all("Portal User", filters={"user": user, "parenttype": "Customer"},
                          pluck="parent", order_by="creation asc", limit=1)
    return rows[0] if rows else None


def require_customer() -> str:
    customer = customer_for_user()
    if not customer:
        frappe.throw(_("Please sign in with a customer account"), frappe.PermissionError)
    if frappe.db.get_value("Customer", customer, "disabled"):
        frappe.throw(_("This account is closed"), frappe.PermissionError)
    return customer


def get_customer_case(case_name: str, for_update: bool = False):
    """Return the case only if it belongs to the signed-in customer.

    Missing and foreign cases are indistinguishable to the caller (no enumeration)."""
    customer = require_customer()
    try:
        doc = frappe.get_doc("AO Application Case", case_name, for_update=for_update) \
            if for_update else frappe.get_doc("AO Application Case", case_name)
    except frappe.DoesNotExistError:
        frappe.throw(_("Case not found"), frappe.DoesNotExistError)
    if doc.customer != customer or doc.deletion_status == "Deleted":
        frappe.throw(_("Case not found"), frappe.DoesNotExistError)
    return doc


def customer_email(customer: str) -> str | None:
    user = frappe.db.get_value("Portal User", {"parent": customer, "parenttype": "Customer"}, "user")
    return frappe.db.get_value("User", user, "email") if user else None


def split_csv(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def check_rate(name: str, user: str, limit: int, seconds: int):
    """Fixed-window counter in Redis. Raises RateLimitExceededError when exceeded."""
    key = frappe.cache.make_key(f"ao_rl:{name}:{user}:{seconds}")
    if not frappe.cache.get(key):
        frappe.cache.setex(key, seconds, 0)
    if frappe.cache.incrby(key, 1) > limit:
        frappe.throw(_("Too many requests. Please try again later."), frappe.RateLimitExceededError)


def user_rate_limit(limit: int, seconds: int):
    """Per-signed-in-user limit for whitelisted methods (Frappe's own decorator is IP/form-field based)."""
    import functools

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if getattr(frappe.local, "request", None) is not None:
                check_rate(fn.__name__, frappe.session.user, limit, seconds)
            return fn(*a, **kw)
        return wrapper
    return deco
