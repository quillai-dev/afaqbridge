import frappe
from frappe import _
from frappe.model.document import Document


class AOAuditEvent(Document):
    def validate(self):
        if not self.is_new() or not self.flags.ao_internal:
            frappe.throw(_("Audit events are append-only"), frappe.PermissionError)

    def on_trash(self):
        frappe.throw(_("Audit events cannot be deleted"), frappe.PermissionError)
