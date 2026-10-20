import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime

from application_office import intake


class AOProgram(Document):
    def validate(self):
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(self.time_zone)
        except Exception:
            frappe.throw(_("{0} is not a valid IANA time zone").format(self.time_zone))
        if self.opening_datetime and self.closing_datetime and get_datetime(self.closing_datetime) <= get_datetime(self.opening_datetime):
            frappe.throw(_("The closing date must be after the opening date"))
        if self.published and not self.last_verified_on:
            frappe.throw(_("A program cannot be published without a staff verification date"))
        intake.validate_program_fields(self)
        for tpl in self.form_templates:
            if tpl.signature_required and not tpl.docuseal_template_id:
                frappe.throw(_("A signature-required form needs a DocuSeal template ID"))
