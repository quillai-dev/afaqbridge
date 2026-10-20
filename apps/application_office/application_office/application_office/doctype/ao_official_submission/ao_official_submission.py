from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from application_office import audit
from application_office.common import AO_ROLES, settings, split_csv


class AOOfficialSubmission(Document):
    """Created by a human employee after submitting through the official website themselves.
    The platform never submits anything to an official site."""

    def before_insert(self):
        user = frappe.session.user
        if user == "Guest" or user in split_csv(settings().service_accounts):
            frappe.throw(_("Official submissions can only be recorded by a human employee"), frappe.PermissionError)
        udoc = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
        if user != "Administrator" and (not udoc or not udoc.enabled or udoc.user_type != "System User"):
            frappe.throw(_("Only an enabled employee account can record a submission"), frappe.PermissionError)
        if user != "Administrator" and not ({"AO Case Worker", "AO Administrator"} & set(frappe.get_roles(user))):
            frappe.throw(_("Only authorised case workers may record submissions"), frappe.PermissionError)
        req = getattr(frappe.local, "request", None)
        if req is not None and req.headers.get("Authorization"):
            frappe.throw(_("Submissions cannot be recorded through API tokens"), frappe.PermissionError)
        self.submitted_by = user
        case = frappe.get_doc("AO Application Case", self.case)
        if case.case_state != "READY_FOR_SUBMISSION":
            frappe.throw(_("The case must be in READY_FOR_SUBMISSION (currently {0})").format(case.case_state))
        if frappe.db.exists("AO Official Submission", {"case": self.case}):
            frappe.throw(_("A submission is already recorded for this case"))
        if not self.human_submission_attestation:
            frappe.throw(_("You must attest that you personally submitted the application"))

    def validate(self):
        if get_datetime(self.submission_timestamp) > get_datetime(now_datetime()) + timedelta(minutes=5):
            frappe.throw(_("The submission time cannot be in the future"))
        if not (self.official_confirmation_number or "").strip():
            frappe.throw(_("The official confirmation number is required"))
        if self.evidence_file and not self.evidence_file.startswith("/private/"):
            frappe.throw(_("Evidence must be attached as a private file"))

    def after_insert(self):
        from application_office.workflow import transition_case
        case = frappe.get_doc("AO Application Case", self.case)
        case.flags.ao_internal = True
        case.official_submission_timestamp = self.submission_timestamp
        case.official_confirmation_reference = self.official_confirmation_number
        case.save(ignore_permissions=True)
        transition_case(self.case, "SUBMITTED", actor_kind="staff", reason="Official submission recorded by employee")
        audit.log("submission.recorded", self.doctype, self.name, self.case,
                  {"portal": self.official_portal, "submitted_by": self.submitted_by})

    def on_update(self):
        if self.has_value_changed("customer_visible_update") and self.customer_visible_update and not self.is_new():
            case = frappe.get_doc("AO Application Case", self.case)
            from application_office.notifications import notify_case
            notify_case("official_update", case, dedupe_key=f"{self.name}:upd:{frappe.generate_hash(length=6)}",
                        message=self.customer_visible_update)
            audit.log("submission.update_entered", self.doctype, self.name, self.case)

    def on_trash(self):
        frappe.throw(_("Submission records cannot be deleted"), frappe.PermissionError)
