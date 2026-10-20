import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_years, getdate, today

from application_office import retention, staff_api
from application_office.tests.utils import *  # noqa: F401,F403


class TestRetention(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_ao_settings()
        cls.worker = make_staff("retw", "AO Case Worker")
        cls.reviewer = make_staff("retr", "AO Reviewer")
        cls.admin = make_staff("reta", "AO Administrator")
        cls.program = make_program().name

    def _closed_case(self, cust):
        case = drive_to_ready_for_submission(self.program, cust, self.worker, self.reviewer)
        with as_user(self.worker):
            frappe.get_doc({"doctype": "AO Official Submission", "case": case, "human_submission_attestation": 1,
                            "official_portal": "x", "submission_timestamp": frappe.utils.now_datetime(),
                            "official_confirmation_number": "R-1"}).insert()
            for st in ("COMPLETED", "CLOSED"):
                staff_api.transition(case, st)
        frappe.get_doc({"doctype": "AO Case Message", "case": case, "visibility": "Customer", "direction": "Staff",
                        "author": self.worker, "body": "hello"}).insert(ignore_permissions=True)
        return case

    def test_retention_period_from_rules(self):
        cust, _ = make_customer("ret1")
        case = self._closed_case(cust)
        doc = frappe.get_doc("AO Application Case", case)
        self.assertEqual(getdate(doc.retention_until), add_years(getdate(today()), 7))  # max of 2,3,7,7,3
        s = frappe.get_doc("AO Settings")
        for r in s.retention_rules:
            if r.retention_category in ("Form / Approval", "Submission Evidence"):
                r.years = 1
        s.save(ignore_permissions=True)
        self.assertEqual(getdate(retention.compute_retention_until(doc)), add_years(getdate(today()), 3))

    def test_eligibility_flag_deletion_and_skeleton(self):
        cust, cust_name = make_customer("ret2")
        case = self._closed_case(cust)
        self.assertEqual(retention.flag_eligible_cases().count(case), 0)  # not elapsed
        frappe.db.set_value("AO Application Case", case, "retention_until", add_days(today(), -1))
        self.assertIn(case, retention.flag_eligible_cases())
        self.assertEqual(frappe.db.get_value("AO Application Case", case, "deletion_status"), "Eligible")
        files = frappe.get_all("File", filters={"attached_to_doctype": "AO Required Document",
                                                "attached_to_name": ["in", frappe.get_all("AO Required Document", filters={"case": case}, pluck="name")]}, pluck="name")
        self.assertTrue(files)
        with as_user(self.worker), self.assertRaises(frappe.PermissionError):
            staff_api.delete_case_data(case)
        frappe.db.set_value("AO Application Case", case, "legal_hold", 1)
        with as_user(self.admin), self.assertRaises(frappe.ValidationError):
            staff_api.delete_case_data(case)
        frappe.db.set_value("AO Application Case", case, "legal_hold", 0)
        with as_user(self.admin):
            res = staff_api.delete_case_data(case)
        self.assertGreaterEqual(res["files_removed"], 2)
        for f in files:
            self.assertFalse(frappe.db.exists("File", f))
        doc = frappe.get_doc("AO Application Case", case)
        self.assertEqual((doc.deletion_status, doc.intake_data), ("Deleted", None))
        self.assertTrue(doc.state_log)  # skeleton kept
        self.assertEqual(frappe.db.count("AO Case Message", {"case": case}), 0)
        self.assertEqual(frappe.db.count("AO Document Version", {"parent": ["in", frappe.get_all("AO Required Document", filters={"case": case}, pluck="name")]}), 0)
        self.assertTrue(frappe.db.exists("AO Audit Event", {"action": "retention.deleted", "case": case}))
        # a deleted case is invisible to the customer
        from application_office import portal_api
        with as_user(cust), self.assertRaises(frappe.DoesNotExistError):
            portal_api.get_case(case)

    def test_open_or_unelapsed_case_cannot_be_deleted(self):
        cust, _ = make_customer("ret3")
        case = start_case_for(cust, self.program)
        with as_user(self.admin), self.assertRaises(frappe.ValidationError):
            staff_api.delete_case_data(case)

    def test_erasure_blocked_by_cases_then_allowed(self):
        cust, cust_name = make_customer("ret4")
        ref = frappe.db.get_value("Customer", cust_name, "ao_customer_reference")
        case = start_case_for(cust, self.program)
        with as_user(self.admin):
            res = retention.execute_erasure(cust_name)
        self.assertFalse(res["erased"]); self.assertTrue(res["blockers"])
        frappe.db.set_value("AO Application Case", case, "deletion_status", "Deleted")
        with as_user(self.admin):
            res = retention.execute_erasure(cust_name)
        self.assertTrue(res["erased"])
        self.assertFalse(frappe.db.exists("User", cust))
        self.assertFalse(frappe.db.exists("Customer", cust_name))  # personal name no longer a primary key
        row = frappe.db.get_value("Customer", ref, ["disabled", "customer_name", "ao_account_status"], as_dict=True)
        self.assertEqual(row.disabled, 1)
        self.assertNotIn("ret4", row.customer_name.lower())
        self.assertEqual(row.ao_account_status, "Closed")

    def test_data_request_logged(self):
        from application_office import portal_api
        cust, cust_name = make_customer("ret5")
        with as_user(cust):
            r = portal_api.data_request("Access / Export", "please")
            with self.assertRaises(frappe.ValidationError):
                portal_api.data_request("Bogus")
        self.assertEqual(frappe.db.get_value("AO Data Request", r["request"], "customer"), cust_name)
