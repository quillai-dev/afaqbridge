import frappe
from frappe import _
from frappe.model.document import Document


class AOCaseMessage(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw(_("Messages cannot be edited"), frappe.PermissionError)
        if self.direction == "Customer" and self.visibility != "Customer":
            frappe.throw(_("Customer messages are always customer-visible"))
