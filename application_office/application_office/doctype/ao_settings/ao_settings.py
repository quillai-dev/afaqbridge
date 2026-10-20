import frappe
from frappe import _
from frappe.model.document import Document


class AOSettings(Document):
    def validate(self):
        for d in (self.reminder_days or "").split(","):
            if d.strip() and not d.strip().isdigit():
                frappe.throw(_("Reminder days must be a comma separated list of numbers"))
        allowed = {"pdf", "jpg", "jpeg", "png"}
        exts = {e.strip().lower().lstrip(".") for e in (self.allowed_extensions or "").split(",") if e.strip()}
        if not exts or exts - allowed:
            frappe.throw(_("Allowed extensions can only be a subset of: {0}").format(", ".join(sorted(allowed))))
        if not 1 <= int(self.max_upload_mb or 0) <= 50:
            frappe.throw(_("Maximum upload size must be between 1 and 50 MB"))
        if self.docuseal_enabled:
            url = (self.docuseal_base_url or "").strip()
            if not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
                frappe.throw(_("DocuSeal URL must use HTTPS (plain HTTP only for localhost)"))
