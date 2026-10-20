import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

from application_office import audit
from application_office.common import AO_ROLES


class AOApplicationCase(Document):
    def validate(self):
        if self.is_new():
            program = frappe.get_doc("AO Program", self.program)
            if not program.published or not program.service_available:
                frappe.throw(_("Program {0} is not currently available for new cases").format(self.program))
            self.customer_approval_required = program.customer_approval_required
            if not self.applicable_deadline and program.closing_datetime:
                self.applicable_deadline = program.closing_datetime
            self.case_state = "NEW"
            self.final_customer_approval_status = "Not Requested"
            self.append("state_log", {"from_state": "", "to_state": "NEW", "actor": frappe.session.user,
                                      "changed_at": frappe.utils.now_datetime(), "reason": "Case created"})
        else:
            if self.has_value_changed("case_state") and not self.flags.ao_transition:
                frappe.throw(_("Workflow state can only be changed through the workflow engine"), frappe.PermissionError)
            # Staff may not forge approval/submission fields through a form save.
            if not self.flags.ao_transition and not self.flags.ao_internal:
                for f in ("final_customer_approval_status", "approved_by_user", "approved_on", "approved_data_hash",
                          "official_submission_timestamp", "official_confirmation_reference", "closure_date",
                          "intake_data", "intake_completed", "retention_until", "deletion_status"):
                    if self.has_value_changed(f):
                        frappe.throw(_("{0} is system-managed and cannot be edited directly").format(f),
                                     frappe.PermissionError)
        if self.assigned_employee:
            roles = set(frappe.get_roles(self.assigned_employee))
            if not (roles & set(AO_ROLES)):
                frappe.throw(_("{0} has no office role and cannot be assigned cases").format(self.assigned_employee))
            if self.has_value_changed("assigned_employee") and not self.is_new():
                audit.log("case.assigned", self.doctype, self.name, self.name, {"to": self.assigned_employee})

    def after_insert(self):
        program = frappe.get_doc("AO Program", self.program)
        for req in program.document_requirements:
            frappe.get_doc({"doctype": "AO Required Document", "case": self.name,
                            "document_category": req.document_category, "required": req.required,
                            "retention_category": req.retention_category, "instructions": req.instructions
                            }).insert(ignore_permissions=True)
        for tpl in program.form_templates:
            frappe.get_doc({"doctype": "AO Form Approval", "case": self.name, "form_template": tpl.form_name,
                            "approval_mode": "DocuSeal Signature" if tpl.signature_required else "In-Portal Approval",
                            "docuseal_template_id": tpl.docuseal_template_id,
                            "signature_status": "Pending" if tpl.signature_required else "Not Applicable"}
                           ).insert(ignore_permissions=True)
        self.db_set("opening_date", self.opening_date or today(), update_modified=False)
        audit.log("case.created", self.doctype, self.name, self.name, {"program": self.program})
        from application_office.notifications import notify_case
        notify_case("application_received", self, dedupe_key=f"{self.name}:application_received")
