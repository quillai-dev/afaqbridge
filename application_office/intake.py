"""Program-defined intake forms. Fields flagged `sensitive` are encrypted at rest with the site
encryption key and are masked for staff until a reveal is explicitly requested (and audited)."""
from __future__ import annotations

import json
import re

import frappe
from frappe import _
from frappe.utils import getdate
from frappe.utils.password import decrypt, encrypt

_KEY = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
MASK = "••••••"


def validate_program_fields(program):
    seen = set()
    for f in program.intake_fields:
        if not _KEY.match(f.field_key or ""):
            frappe.throw(_("Intake field key '{0}' must be lowercase letters, digits and underscores").format(f.field_key))
        if f.field_key in seen:
            frappe.throw(_("Duplicate intake field key {0}").format(f.field_key))
        seen.add(f.field_key)


def _coerce(f, value):
    if f.field_type == "Checkbox":
        return 1 if value in (1, True, "1", "true", "on") else 0
    if value is None:
        return ""
    value = str(value).strip()
    if len(value) > 5000:
        frappe.throw(_("{0} is too long").format(f.label))
    if f.field_type == "Date" and value:
        try:
            getdate(value)
        except Exception:
            frappe.throw(_("{0} must be a valid date").format(f.label))
    if f.field_type == "Select" and value:
        options = [o.strip() for o in (f.options or "").splitlines() if o.strip()]
        if value not in options:
            frappe.throw(_("Invalid choice for {0}").format(f.label))
    return value


def store(case, values: dict, complete: bool):
    """Validate against the program definition and persist. Unknown keys are rejected."""
    program = frappe.get_cached_doc("AO Program", case.program)
    defs = {f.field_key: f for f in program.intake_fields}
    unknown = set(values) - set(defs)
    if unknown:
        frappe.throw(_("Unknown intake fields: {0}").format(", ".join(sorted(unknown))))
    current = json.loads(case.intake_data or "{}")
    for key, f in defs.items():
        if key in values:
            v = _coerce(f, values[key])
            current[key] = encrypt(v) if (f.sensitive and v not in ("", None)) else v
    if complete:
        missing = [f.label for f in defs.values() if f.required and
                   (current.get(f.field_key) in (None, "", 0) and f.field_type != "Checkbox"
                    or f.field_type == "Checkbox" and not current.get(f.field_key))]
        if missing:
            frappe.throw(_("Required information missing: {0}").format(", ".join(missing)))
    case.intake_data = json.dumps(current)
    case.intake_completed = 1 if complete else 0


def read(case, reveal: bool = False, program=None) -> list[dict]:
    program = program or frappe.get_cached_doc("AO Program", case.program)
    data = json.loads(case.intake_data or "{}")
    out = []
    for f in program.intake_fields:
        raw = data.get(f.field_key, "")
        if f.sensitive and raw not in ("", None):
            value = decrypt(raw) if reveal else MASK
        else:
            value = raw
        out.append({"field_key": f.field_key, "label": f.label, "field_type": f.field_type,
                    "required": f.required, "sensitive": f.sensitive,
                    "options": [o for o in (f.options or "").splitlines() if o.strip()], "value": value})
    return out
