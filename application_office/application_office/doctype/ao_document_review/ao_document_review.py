import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from application_office import audit


class AODocumentReview(Document):
    def before_insert(self):
        rd = frappe.get_doc("AO Required Document", self.required_document)
        if rd.upload_status != "Uploaded" or not rd.current_version:
            frappe.throw(_("There is no uploaded document to review"))
        self.reviewer = frappe.session.user
        self.review_date = now_datetime()
        self.version_reviewed = rd.current_version
        self.case = rd.case

    def validate(self):
        if not self.is_new():
            frappe.throw(_("Reviews are immutable; add a new review instead"), frappe.PermissionError)
        if self.decision == "Correction Required" and not (self.requested_corrections or self.customer_feedback):
            frappe.throw(_("Describe the corrections the customer must make"))

    def after_insert(self):
        rd = frappe.get_doc("AO Required Document", self.required_document)
        rd.flags.ao_internal = True
        rd.review_status = self.decision
        rd.reviewer = self.reviewer
        rd.review_timestamp = self.review_date
        rd.rejection_reason = self.findings if self.decision != "Approved" else None
        rd.customer_feedback = self.customer_feedback or self.requested_corrections
        rd.save(ignore_permissions=True)
        audit.log("document.reviewed", self.doctype, self.name, rd.case,
                  {"decision": self.decision, "version": self.version_reviewed, "document": rd.name})
        case = frappe.get_doc("AO Application Case", rd.case)
        from application_office.notifications import notify_case
        notify_case("review_complete", case, dedupe_key=f"{self.name}:review_complete",
                    message=rd.customer_feedback if self.decision != "Approved" else None)

    def on_trash(self):
        if not frappe.flags.in_test and not self.flags.ao_internal:
            frappe.throw(_("Reviews cannot be deleted"), frappe.PermissionError)
