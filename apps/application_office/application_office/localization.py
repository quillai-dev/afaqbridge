"""Arabic-first localisation for AfaqBridge.

Uses Frappe's own mechanisms (System Settings language, the `preferred_language` cookie, per-user language,
gettext .po files in ./locale). The only custom behaviour is the *initial* language of an anonymous visitor:
stock Frappe lets the browser's Accept-Language header win over System Settings, so an English browser
would get English on first visit. `before_request` below makes Arabic the initial language for guests who
have not chosen one yet; an explicit choice (cookie / ?_lang=) is never overridden.
"""
from __future__ import annotations

import frappe

DEFAULT_LANGUAGE = "ar"
SUPPORTED_LANGUAGES = ("ar", "en")
COOKIE = "preferred_language"
_SKIP_PREFIXES = ("/assets", "/files", "/private", "/socket.io", "/api/method/ping")


def normalise(lang: str | None) -> str | None:
    """'ar-SA' / 'AR' -> 'ar'; anything unsupported -> None."""
    code = (lang or "").replace("_", "-").split("-")[0].strip().lower()
    return code if code in SUPPORTED_LANGUAGES else None


def before_request():
    """Fresh anonymous visitor (no cookie, no ?_lang=): Arabic, whatever Accept-Language says."""
    request = getattr(frappe.local, "request", None)
    if request is None or frappe.session.user != "Guest":
        return
    if frappe.form_dict.get("_lang") or request.cookies.get(COOKIE):
        return
    if request.path.startswith(_SKIP_PREFIXES):
        return
    frappe.local.lang = DEFAULT_LANGUAGE
    frappe.local.ao_set_language_cookie = True


def after_request(response, request):
    """Persist the initial choice so Frappe's language picker shows the language that is actually rendered."""
    if not getattr(frappe.local, "ao_set_language_cookie", False):
        return
    if "text/html" not in (response.headers.get("Content-Type") or ""):
        return
    response.set_cookie(COOKIE, DEFAULT_LANGUAGE, path="/", max_age=365 * 24 * 3600, samesite="Lax",
                        secure=request.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https")


def default_language_for_new_user() -> str:
    """Language for a newly created account: the language the visitor is currently using, else Arabic."""
    return normalise(getattr(frappe.local, "lang", None)) or DEFAULT_LANGUAGE


def user_before_insert(doc, method=None):
    """New accounts start in Arabic (or in the language the registrant was already viewing)."""
    if not doc.get("language"):
        doc.language = default_language_for_new_user()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def set_language(lang: str):
    """Switch between Arabic and English. Guests: cookie only. Signed-in users: also their User.language, so the
    choice survives new sessions. The page URL is unchanged: the client reloads in place."""
    code = normalise(lang)
    if not code:
        frappe.throw(frappe._("Unsupported language"), frappe.ValidationError)
    if frappe.session.user != "Guest":
        frappe.db.set_value("User", frappe.session.user, "language", code, update_modified=False)
    frappe.local.cookie_manager.set_cookie(COOKIE, code)
    return {"language": code}


from contextlib import contextmanager


@contextmanager
def language(lang: str | None):
    """Render text (e-mails, status labels) in a specific language, e.g. the recipient's, then restore."""
    previous = getattr(frappe.local, "lang", None)
    frappe.local.lang = normalise(lang) or DEFAULT_LANGUAGE
    try:
        yield
    finally:
        frappe.local.lang = previous


def translate_if_default(stored: str | None, default: str) -> str:
    """AO Settings holds ONE text per field. While it still equals the shipped default it is translated into the
    viewer's language; once an administrator edits it, their text is shown verbatim."""
    from frappe import _
    from frappe.utils import strip_html
    plain_default = strip_html(default)
    plain = strip_html(stored or "")
    return _(plain_default) if plain == plain_default or not plain else plain
