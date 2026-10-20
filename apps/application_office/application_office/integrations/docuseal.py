"""DocuSeal integration (verified against upstream docuseal 3.3.2 source).

Facts relied on (see docs/integration-plan.md):
* Auth to DocuSeal API:     header `X-Auth-Token: <api token>`
* Create signing request:   POST /api/submissions {template_id, send_email, submitters:[{role,email,name,external_id}]}
                            -> list of submitters incl. id, submission_id, slug, embed_src, external_id
* Webhook signature:        header `X-Docuseal-Signature: <ts>.<hex HMAC-SHA256(secret, "<ts>.<raw body>")>`,
                            tolerance +/-300 s (lib/webhook_urls/signatures.rb). DocuSeal also supports static
                            custom headers; we rely on the HMAC.
* Webhook body:             {event_type, timestamp, data:{...}} ; retried by DocuSeal up to 12x on non-2xx.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlparse

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, now_datetime

from application_office import audit
from application_office.common import settings

TOLERANCE_SECONDS = 300
MAX_ATTEMPTS = 5
TIMEOUT = (5, 20)


def _commit():
    """Persist before returning/raising in a real request; tests keep their transaction (rolled back per class)."""
    if not frappe.flags.in_test:
        frappe.db.commit()


class SignatureError(Exception):
    pass


def verify_signature(secret: str, body: bytes, header: str | None, now: float | None = None,
                     tolerance: int = TOLERANCE_SECONDS) -> bool:
    """Mirror of DocuSeal's WebhookUrls::Signatures.verify. Raises SignatureError."""
    if not secret or not header:
        raise SignatureError("missing")
    ts_raw, _, sig = header.partition(".")
    try:
        ts = int(ts_raw)
    except ValueError:
        raise SignatureError("malformed") from None
    if not sig:
        raise SignatureError("malformed")
    now = time.time() if now is None else now
    if ts < now - tolerance or ts > now + tolerance:
        raise SignatureError("timestamp")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise SignatureError("mismatch")
    return True


def sign(secret: str, body: bytes, ts: int | None = None) -> str:
    """Produce a header in DocuSeal's format (used by tests and the contract-test double)."""
    ts = int(time.time()) if ts is None else ts
    return f"{ts}.{hmac.new(secret.encode(), f'{ts}.'.encode() + body, hashlib.sha256).hexdigest()}"


# ---------------------------------------------------------------- webhook receiver
def _respond(status: int, message: str):
    frappe.local.response["http_status_code"] = status
    return {"message": message}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=600, seconds=60)
def webhook():
    s = settings()
    secret = s.get_password("docuseal_webhook_secret", raise_exception=False)
    if not s.docuseal_enabled or not secret:
        return _respond(503, "disabled")
    body = frappe.request.get_data(cache=True)
    if len(body) > 1_000_000:
        return _respond(413, "too large")
    try:
        verify_signature(secret, body, frappe.get_request_header("X-Docuseal-Signature"))
    except SignatureError as e:
        frappe.log_error(title="DocuSeal webhook rejected", message=f"reason={e}")  # never log the body
        return _respond(401, "invalid signature")
    try:
        payload = json.loads(body)
        event_type = str(payload["event_type"])
        data = payload["data"]
        ev_id = str(data["id"])
        stamp = str(payload.get("timestamp", ""))
    except Exception:
        return _respond(400, "malformed")
    ctx = {"event_type": event_type, "id": ev_id, "submission_id": str((data.get("submission") or {}).get("id") or data.get("submission_id") or ""),
           "external_id": str(data.get("external_id") or ""), "status": str(data.get("status") or "")}
    event_key = f"docuseal:{event_type}:{ev_id}:{stamp}"
    try:
        ev = frappe.get_doc({"doctype": "AO Integration Event", "event_key": event_key, "source": "docuseal",
                             "event_type": event_type, "status": "Received", "attempts": 0,
                             "received_at": now_datetime(), "context": json.dumps(ctx),
                             "payload_digest": hashlib.sha256(body).hexdigest()})
        ev.insert(ignore_permissions=True)
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        return _respond(200, "duplicate")
    _commit()
    frappe.enqueue("application_office.integrations.docuseal.process_event", event_name=ev.name,
                   queue="short", enqueue_after_commit=True)
    return _respond(200, "accepted")


# ---------------------------------------------------------------- event processing (idempotent)
def process_event(event_name: str):
    ev = frappe.get_doc("AO Integration Event", event_name)
    if ev.status in ("Processed", "Ignored"):
        return
    ctx = json.loads(ev.context or "{}")
    ev.attempts = cint(ev.attempts) + 1
    try:
        result = _apply(ctx)
        ev.status = "Processed" if result else "Ignored"
        ev.error = None
    except Exception as e:
        ev.status = "Error"
        ev.error = f"{type(e).__name__}: {str(e)[:200]}"
        frappe.log_error(title="DocuSeal event processing failed", message=f"{ev.event_key} {type(e).__name__}")
    ev.save(ignore_permissions=True)
    _commit()


def retry_failed_events():
    for name in frappe.get_all("AO Integration Event", filters={"status": "Error", "attempts": ["<", MAX_ATTEMPTS],
                                                                "source": "docuseal"}, pluck="name", limit=50):
        process_event(name)


def _find_form(ctx: dict):
    ext = ctx.get("external_id")
    if ext and frappe.db.exists("AO Form Approval", ext):
        return frappe.get_doc("AO Form Approval", ext, for_update=True)
    sid = ctx.get("submission_id") or (ctx["id"] if ctx["event_type"].startswith("submission.") else None)
    name = frappe.db.get_value("AO Form Approval", {"docuseal_submission_id": sid}, "name") if sid else None
    return frappe.get_doc("AO Form Approval", name, for_update=True) if name else None


def _apply(ctx: dict) -> bool:
    et = ctx["event_type"]
    fa = _find_form(ctx)
    if not fa:
        return False
    rank = {"Pending": 0, "Sent": 1, "Viewed": 2, "Expired": 3, "Declined": 3, "Completed": 4, "Error": 0}
    cur = fa.submission_status

    def advance(new):
        if rank.get(new, 0) > rank.get(cur, 0):
            fa.submission_status = new

    if et in ("form.viewed", "form.started"):
        advance("Viewed")
    elif et == "form.completed":
        if fa.signature_status != "Signed":
            fa.signature_status = "Signed"
            fa.customer_approval = 1
            fa.approval_timestamp = now_datetime()
            if ctx.get("id"):
                fa.docuseal_submitter_id = ctx["id"]
        fa.submission_status = "Completed"
        fa.flags.ao_internal = True
        fa.save(ignore_permissions=True)
        _store_signed_document(fa)
        audit.log("docuseal.completed", fa.doctype, fa.name, fa.case)
        from application_office.portal_api import maybe_advance_after_approval
        maybe_advance_after_approval(fa.case)
        return True
    elif et == "form.declined":
        if fa.signature_status != "Signed":
            advance("Declined")
            fa.signature_status = "Declined"
    elif et == "submission.expired":
        advance("Expired")
    elif et == "submission.completed":
        advance("Completed")
    else:
        return False
    fa.save(ignore_permissions=True)
    audit.log(f"docuseal.{et}", fa.doctype, fa.name, fa.case)
    return True


# ---------------------------------------------------------------- outgoing API
def _base() -> tuple[str, str]:
    s = settings()
    if not s.docuseal_enabled:
        raise frappe.ValidationError(_("DocuSeal integration is disabled"))
    token = s.get_password("docuseal_api_token", raise_exception=False)
    base = (s.docuseal_base_url or "").rstrip("/")
    if not token or not base:
        raise frappe.ValidationError(_("DocuSeal is not configured"))
    return base, token


def _request(method: str, path: str, *, json_body=None, stream=False, absolute: str | None = None):
    """HTTP call with timeouts and bounded retry (connection errors / 5xx only)."""
    base, token = _base()
    url = absolute or base + path
    if absolute and urlparse(absolute).netloc != urlparse(base).netloc:
        raise frappe.ValidationError("Refusing to fetch from a foreign host")
    last, last_resp = None, None
    for attempt in range(3):
        try:
            r = requests.request(method, url, json=json_body, headers={"X-Auth-Token": token, "Accept": "application/json"},
                                 timeout=TIMEOUT, stream=stream, allow_redirects=False)
            if r.status_code >= 500:
                last, last_resp = RuntimeError(f"DocuSeal HTTP {r.status_code}"), r
                time.sleep(min(2 ** attempt, 4) if not frappe.flags.in_test else 0)
                continue
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last = e
            time.sleep(min(2 ** attempt, 4) if not frappe.flags.in_test else 0)
    if last_resp is not None:
        return last_resp
    raise ConnectionError(f"DocuSeal unreachable: {type(last).__name__}")


def create_signing_request(form_approval: str) -> str:
    """Create (once) the DocuSeal submission and return the signing URL. Failures are recorded on the
    Form Approval and re-raised as a friendly error; they never affect other cases."""
    fa = frappe.get_doc("AO Form Approval", form_approval, for_update=True)
    if fa.approval_mode != "DocuSeal Signature":
        raise frappe.ValidationError(_("This form does not use DocuSeal"))
    if fa.docuseal_signing_url:
        return fa.docuseal_signing_url
    if not (fa.docuseal_template_id or "").isdigit():
        raise frappe.ValidationError(_("The DocuSeal template ID is invalid"))
    from application_office.common import customer_email
    email = customer_email(fa.customer)
    try:
        r = _request("POST", "/api/submissions", json_body={
            "template_id": int(fa.docuseal_template_id), "send_email": False,
            "submitters": [{"role": settings().docuseal_signer_role or "First Party", "email": email,
                            "name": frappe.db.get_value("Customer", fa.customer, "customer_name"),
                            "external_id": fa.name}]})
        if r.status_code >= 400:
            raise RuntimeError(f"DocuSeal HTTP {r.status_code}")
        data = r.json()
        submitters = data if isinstance(data, list) else data.get("submitters", [])
        sub = next((x for x in submitters if x.get("external_id") == fa.name), submitters[0] if submitters else None)
        if not sub or not sub.get("embed_src"):
            raise RuntimeError("Unexpected DocuSeal response")
    except Exception as e:
        fa.submission_status = "Error"
        fa.last_error = f"{type(e).__name__}: {str(e)[:150]}"
        fa.flags.ao_internal = True
        fa.save(ignore_permissions=True)
        _commit()
        audit.log("docuseal.create_failed", fa.doctype, fa.name, fa.case, {"error": type(e).__name__})
        raise frappe.ValidationError(_("The signing service is temporarily unavailable. Please try again later.")) from e
    fa.docuseal_submission_id = str(sub.get("submission_id") or "")
    fa.docuseal_submitter_id = str(sub.get("id") or "")
    fa.docuseal_signing_url = sub["embed_src"]
    fa.submission_status = "Sent"
    fa.signature_status = "Pending"
    fa.last_error = None
    fa.save(ignore_permissions=True)
    audit.log("docuseal.created", fa.doctype, fa.name, fa.case)
    return fa.docuseal_signing_url


def _store_signed_document(fa):
    """Fetch the signed PDF through the authenticated API and keep it as a PRIVATE file."""
    if fa.signed_document_file or not fa.docuseal_submission_id:
        return
    try:
        r = _request("GET", f"/api/submissions/{int(fa.docuseal_submission_id)}/documents")
        docs = r.json().get("documents", []) if r.status_code == 200 else []
        if not docs:
            return
        pdf = _request("GET", "", absolute=docs[0]["url"], stream=True)
        content = pdf.raw.read(20 * 1024 * 1024 + 1) if pdf.status_code == 200 else b""
        if not content.startswith(b"%PDF-") or len(content) > 20 * 1024 * 1024:
            return
        f = frappe.get_doc({"doctype": "File", "file_name": f"{fa.name}-signed.pdf", "is_private": 1, "content": content,
                            "attached_to_doctype": "AO Form Approval", "attached_to_name": fa.name})
        f.insert(ignore_permissions=True)
        frappe.db.set_value("AO Form Approval", fa.name, "signed_document_file", f.name)
    except Exception as e:
        # The signature itself is already recorded; the copy can be fetched again by staff later.
        frappe.log_error(title="DocuSeal signed document fetch failed", message=type(e).__name__)
