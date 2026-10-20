import frappe
from frappe import _
from frappe.model.document import Document


class AORequiredDocument(Document):
    def validate(self):
        if not self.is_new() and not (self.flags.ao_internal or frappe.flags.in_install):
            for f in ("upload_status", "review_status", "current_version", "reviewer", "review_timestamp",
                      "customer_feedback", "rejection_reason"):
                if self.has_value_changed(f):
                    frappe.throw(_("{0} is managed by the upload/review process").format(f), frappe.PermissionError)
            old = self.get_doc_before_save()
            if old and [(v.version, v.sha256) for v in old.versions] != [(v.version, v.sha256) for v in self.versions]:
                frappe.throw(_("Document versions are immutable"), frappe.PermissionError)
