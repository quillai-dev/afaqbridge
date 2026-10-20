"""Append-only audit trail. Details are sanitised so secrets never reach the log."""
from __future__ import annotations

import json
import re

import frappe
from frappe.utils import now_datetime

_SENSITIVE = re.compile(r"(pass(word|port)?|secret|token|api_?key|authorization|intake|hash_key|card|iban|ssn)", re.I)
_MAX_LEN = 500


def sanitize(value, _depth=0):
    if _depth > 4:
        return "…"
    if isinstance(value, dict):
        return {k: ("***" if _SENSITIVE.search(str(k)) else sanitize(v, _depth + 1)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, _depth + 1) for v in value[:50]]
    if isinstance(value, str) and len(value) > _MAX_LEN:
        return value[:_MAX_LEN] + "…"
    return value


def log(action: str, ref_doctype: str | None = None, ref_name: str | None = None,
        case: str | None = None, details: dict | None = None, actor: str | None = None):
    doc = frappe.get_doc({
        "doctype": "AO Audit Event",
        "event_time": now_datetime(),
        "actor": actor or frappe.session.user,
        "action": action,
        "ref_doctype": ref_doctype,
        "ref_name": ref_name,
        "case": case,
        "details": json.dumps(sanitize(details or {}), default=str, ensure_ascii=False),
    })
    doc.flags.ao_internal = True
    doc.insert(ignore_permissions=True)
    return doc.name
