import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from application_office import audit


class AOReferral(Document):
    def validate(self):
        # permlevel-1 fields can only be written by AO Administrators (enforced by Frappe); here we keep
        # the verification metadata consistent and honest.
        if self.licence_verified:
            if not (self.licence_details and self.verification_source):
                frappe.throw(_("Licence details and the register consulted are required to mark a licence verified"))
            if self.has_value_changed("licence_verified"):
                self.verified_by = frappe.session.user
                self.verification_date = today()
        else:
            self.verified_by = self.verification_date = None
        if self.has_value_changed("licence_verified"):
            audit.log("referral.licence_verification", self.doctype, self.name or "new", self.case,
                      {"verified": bool(self.licence_verified)})

    def after_insert(self):
        audit.log("referral.created", self.doctype, self.name, self.case, {"jurisdiction": self.jurisdiction})
