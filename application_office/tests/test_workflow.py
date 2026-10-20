import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from application_office import audit, portal_api, staff_api
from application_office.tests.utils import *  # noqa: F401,F403
from application_office.workflow import TransitionError, compute_case_hash, transition_case


class TestWorkflow(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_ao_settings()
        cls.worker = make_staff("w1", "AO Case Worker")
        cls.reviewer = make_staff("r1", "AO Reviewer")
        cls.program = make_program().name
        cls.cust, cls.cust_name = make_customer("alice")

    def test_full_happy_path(self):
        case = drive_to_ready_for_submission(self.program, self.cust, self.worker, self.reviewer)
        doc = frappe.get_doc("AO Application Case", case)
        self.assertEqual(doc.case_state, "READY_FOR_SUBMISSION")
        self.assertEqual(doc.final_customer_approval_status, "Approved")
        self.assertEqual(doc.approved_data_hash, compute_case_hash(doc))
        with as_user(self.worker):
            sub = frappe.get_doc({"doctype": "AO Official Submission", "case": case, "human_submission_attestation": 1,
                                  "official_portal": "https://official.example/apply",
                                  "submission_timestamp": now_datetime(), "official_confirmation_number": "CONF-123"}).insert()
        doc.reload()
        self.assertEqual(doc.case_state, "SUBMITTED")
        self.assertEqual(doc.official_confirmation_reference, "CONF-123")
        self.assertEqual(sub.submitted_by, self.worker)
        with as_user(self.worker):
            for st in ("AWAITING_OFFICIAL_UPDATE", "COMPLETED", "CLOSED"):
                staff_api.transition(case, st)
        doc.reload()
        self.assertEqual(doc.case_state, "CLOSED")
        self.assertTrue(doc.closure_date and doc.retention_until)
        self.assertEqual([l.to_state for l in doc.state_log][:3], ["NEW", "WAITING_FOR_DOCUMENTS", "UNDER_REVIEW"])
        self.assertTrue(all(l.actor and l.changed_at for l in doc.state_log))
        self.assertTrue(frappe.db.exists("AO Audit Event", {"case": case, "action": "submission.recorded"}))
        # notifications: received, approval request, submission recorded, closed
        events = set(frappe.get_all("AO Notification Log", filters={"case": case}, pluck="event_key"))
        self.assertTrue({"application_received", "approval_request", "submission_recorded", "case_closed"} <= events)

    def test_invalid_and_unauthorised_transitions(self):
        case = start_case_for(self.cust, self.program)
        with self.assertRaises(TransitionError):
            transition_case(case, "SUBMITTED", actor_kind="system")
        with as_user(self.worker), self.assertRaises(TransitionError):
            staff_api.transition(case, "COMPLETED")
        # reason required
        with as_user(self.worker), self.assertRaises(TransitionError):
            staff_api.transition(case, "ON_HOLD", "")
        # customer may not perform staff-only transitions
        with as_user(self.cust), self.assertRaises(frappe.PermissionError):
            transition_case(case, "ON_HOLD", reason="x", actor_kind="customer")
        # a reviewer may not put a case on hold (not in role list)
        with as_user(self.reviewer), self.assertRaises(frappe.PermissionError):
            staff_api.transition(case, "ON_HOLD", "no")

    def test_state_cannot_be_edited_directly(self):
        case = start_case_for(self.cust, self.program)
        doc = frappe.get_doc("AO Application Case", case)
        doc.case_state = "SUBMITTED"
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)
        doc = frappe.get_doc("AO Application Case", case)
        doc.final_customer_approval_status = "Approved"
        with self.assertRaises(frappe.PermissionError):
            doc.save(ignore_permissions=True)

    def test_submission_requires_human_attestation_state_and_employee(self):
        case = start_case_for(self.cust, self.program)
        base = {"doctype": "AO Official Submission", "case": case, "official_portal": "x",
                "submission_timestamp": now_datetime(), "official_confirmation_number": "C1"}
        with as_user(self.worker), self.assertRaises(frappe.ValidationError):  # wrong state
            frappe.get_doc({**base, "human_submission_attestation": 1}).insert()
        ready = drive_to_ready_for_submission(self.program, self.cust, self.worker, self.reviewer)
        base["case"] = ready
        with as_user(self.worker), self.assertRaises(frappe.ValidationError):  # no attestation (mandatory)
            frappe.get_doc({**base, "human_submission_attestation": 0}).insert()
        with as_user(self.cust), self.assertRaises(frappe.PermissionError):  # customer
            frappe.get_doc({**base, "human_submission_attestation": 1}).insert()
        with as_user(self.reviewer), self.assertRaises(frappe.PermissionError):  # reviewer role
            frappe.get_doc({**base, "human_submission_attestation": 1}).insert()
        s = frappe.get_doc("AO Settings"); s.service_accounts = self.worker; s.save(ignore_permissions=True)
        with as_user(self.worker), self.assertRaises(frappe.PermissionError):  # flagged bot account
            frappe.get_doc({**base, "human_submission_attestation": 1}).insert()
        s.service_accounts = ""; s.save(ignore_permissions=True)
        with as_user(self.worker), self.assertRaises(frappe.ValidationError):  # missing confirmation number
            frappe.get_doc({**base, "human_submission_attestation": 1, "official_confirmation_number": " "}).insert()

    def test_cannot_ready_for_submission_without_customer_approval(self):
        case = start_case_for(self.cust, self.program)
        fill_intake(self.cust, case); upload_all(case, self.cust); customer_submit(case, self.cust)
        approve_docs(case, self.reviewer)
        with as_user(self.worker), self.assertRaises(TransitionError):
            staff_api.transition(case, "READY_FOR_SUBMISSION")
        with as_user(self.reviewer), self.assertRaises(TransitionError):
            staff_api.transition(frappe.get_doc({"doctype": "AO Application Case", "customer": self.cust_name,
                                                 "program": self.program}).insert(ignore_permissions=True).name,
                                 "UNDER_REVIEW")

    def test_documents_must_be_approved_before_customer_approval(self):
        case = start_case_for(self.cust, self.program)
        fill_intake(self.cust, case); upload_all(case, self.cust); customer_submit(case, self.cust)
        with as_user(self.reviewer), self.assertRaises(TransitionError):
            staff_api.transition(case, "READY_FOR_CUSTOMER_APPROVAL")

    def test_data_change_after_approval_blocks_submission_guard(self):
        from application_office.workflow import check_guards
        case = drive_to_ready_for_submission(self.program, self.cust, self.worker, self.reviewer)
        doc = frappe.get_doc("AO Application Case", case)
        doc.flags.ao_internal = True
        doc.intake_data = doc.intake_data + " "
        doc.save(ignore_permissions=True)
        doc.reload()
        with self.assertRaises(TransitionError):
            check_guards(doc, "READY_FOR_SUBMISSION")

    def test_returning_to_review_resets_approval(self):
        case = drive_to_ready_for_submission(self.program, self.cust, self.worker, self.reviewer)
        with as_user(self.worker):
            staff_api.transition(case, "UNDER_REVIEW", "found an inconsistency")
        doc = frappe.get_doc("AO Application Case", case)
        self.assertEqual(doc.final_customer_approval_status, "Not Requested")
        self.assertFalse(doc.approved_data_hash)

    def test_customer_requests_changes(self):
        case = start_case_for(self.cust, self.program)
        fill_intake(self.cust, case); upload_all(case, self.cust); customer_submit(case, self.cust)
        approve_docs(case, self.reviewer)
        with as_user(self.worker):
            staff_api.transition(case, "READY_FOR_CUSTOMER_APPROVAL")
        with as_user(self.cust):
            portal_api.request_changes(case, "My middle name is missing")
        self.assertEqual(frappe.db.get_value("AO Application Case", case, "case_state"), "CORRECTION_REQUIRED")

    def test_audit_is_append_only_and_sanitised(self):
        name = audit.log("t.test", details={"passport_number": "X999", "ok": "fine", "nested": {"api_token": "abc"}})
        ev = frappe.get_doc("AO Audit Event", name)
        self.assertNotIn("X999", ev.details); self.assertNotIn("abc", ev.details); self.assertIn("fine", ev.details)
        ev.action = "tampered"
        with self.assertRaises(frappe.PermissionError):
            ev.save(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("AO Audit Event", name, ignore_permissions=True, force=True)
