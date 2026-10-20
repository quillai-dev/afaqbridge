import frappe
from frappe import _
from frappe.model.document import Document


class AOWorkflowTransition(Document):
    def validate(self):
        if self.from_state == self.to_state:
            frappe.throw(_("A transition must change state"))
        if self.from_state == "CLOSED":
            frappe.throw(_("CLOSED is terminal"))
        for r in [x.strip() for x in self.allowed_roles.split(",") if x.strip()]:
            if r != "Customer" and not frappe.db.exists("Role", r):
                frappe.throw(_("Unknown role {0}").format(r))
