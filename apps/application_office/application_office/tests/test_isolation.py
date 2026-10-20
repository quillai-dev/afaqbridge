import json

import frappe
from frappe.tests import IntegrationTestCase

from application_office import portal_api, staff_api, uploads
from application_office.tests.utils import *  # noqa: F401,F403


class TestIsolation(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_ao_settings()
        cls.w1 = make_staff("iw1", "AO Case Worker")
        cls.w2 = make_staff("iw2", "AO Case Worker")
        cls.auditor = make_staff("iaud", "AO Auditor")
        cls.finance = make_staff("ifin", "AO Finance")
        cls.reviewer = make_staff("irev", "AO Reviewer")
        cls.admin = make_staff("iadm", "AO Administrator")
        cls.program = make_program().name
        cls.a, cls.a_cust = make_customer("isoa")
        cls.b, cls.b_cust = make_customer("isob")
        cls.case_a = start_case_for(cls.a, cls.program)
        cls.case_b = start_case_for(cls.b, cls.program)
        fill_intake(cls.a, cls.case_a)
        upload_all(cls.case_a, cls.a)
        cls.rd_a = frappe.get_all("AO Required Document", filters={"case": cls.case_a}, pluck="name")[0]

    def test_customer_cannot_read_other_customers_case(self):
        with as_user(self.b):
            for fn in (portal_api.get_case,):
                with self.assertRaises(frappe.DoesNotExistError):
                    fn(self.case_a)
            with self.assertRaises(frappe.DoesNotExistError):
                portal_api.get_case("AC-1999-99999")  # nonexistent == foreign (no enumeration)
            self.assertEqual([c["name"] for c in portal_api.list_cases()], [self.case_b])
            with self.assertRaises(frappe.DoesNotExistError):
                portal_api.download_document(self.case_a, self.rd_a)
            with self.assertRaises(frappe.DoesNotExistError):  # own case id + foreign document id
                portal_api.download_document(self.case_b, self.rd_a)
            with self.assertRaises(frappe.DoesNotExistError):
                portal_api.save_intake(self.case_a, json.dumps({"full_name": "x"}), 0)
            with self.assertRaises(frappe.DoesNotExistError):
                portal_api.send_message(self.case_a, "hi")
            with self.assertRaises(frappe.DoesNotExistError):
                portal_api.approve_case(self.case_a, 1)

    def test_customer_cannot_upload_to_foreign_document(self):
        with as_user(self.b), self.assertRaises(frappe.DoesNotExistError):
            portal_api.upload_document(self.case_a, self.rd_a)
        with as_user(self.b), self.assertRaises(frappe.DoesNotExistError):
            portal_api.upload_document(self.case_b, self.rd_a)  # doc belongs to another case

    def test_customer_has_no_direct_framework_access(self):
        with as_user(self.b):
            for dt, name in (("AO Application Case", self.case_a), ("AO Required Document", self.rd_a),
                             ("AO Program", self.program)):
                self.assertFalse(frappe.has_permission(dt, "read", doc=name), dt)
            with self.assertRaises(frappe.PermissionError):
                frappe.get_list("AO Application Case")
            with self.assertRaises(frappe.PermissionError):
                frappe.get_doc("AO Application Case", self.case_a).check_permission("read")
            f = frappe.db.get_value("File", {"attached_to_name": self.rd_a}, "name")
            self.assertFalse(frappe.has_permission("File", "read", doc=f))  # private file of customer A

    def test_customer_cannot_call_staff_api(self):
        with as_user(self.a):
            for call in (lambda: staff_api.transition(self.case_a, "ON_HOLD", "x"),
                         lambda: staff_api.reveal_intake(self.case_a),
                         lambda: staff_api.review_document(self.rd_a, "Approved"),
                         lambda: staff_api.create_invoice(self.case_a, "[]"),
                         lambda: staff_api.delete_case_data(self.case_a)):
                with self.assertRaises(frappe.PermissionError):
                    call()

    def test_guest_cannot_use_portal_api(self):
        with as_user("Guest"):
            for fn, args in ((portal_api.list_cases, ()), (portal_api.list_services, ()), (portal_api.list_invoices, ())):
                with self.assertRaises(frappe.PermissionError):
                    fn(*args)

    def test_case_worker_row_level_access(self):
        frappe.db.set_value("AO Application Case", self.case_a, "assigned_employee", self.w1)
        with as_user(self.w1):
            self.assertTrue(frappe.has_permission("AO Application Case", "read", doc=self.case_a))
        with as_user(self.w2):
            self.assertFalse(frappe.has_permission("AO Application Case", "read", doc=self.case_a))
            self.assertNotIn(self.case_a, [c.name for c in frappe.get_list("AO Application Case")])
            self.assertFalse(frappe.has_permission("AO Required Document", "read", doc=self.rd_a))
            self.assertNotIn(self.rd_a, [c.name for c in frappe.get_list("AO Required Document")])
            with self.assertRaises(frappe.PermissionError):
                staff_api.transition(self.case_a, "ON_HOLD", "x")
            self.assertIn(self.case_b, [c.name for c in frappe.get_list("AO Application Case")])  # unassigned visible
        frappe.db.set_value("AO Application Case", self.case_a, "assigned_employee", None)

    def test_role_matrix(self):
        with as_user(self.auditor):
            self.assertTrue(frappe.has_permission("AO Application Case", "read", doc=self.case_a))
            self.assertFalse(frappe.has_permission("AO Application Case", "write", doc=self.case_a))
            self.assertFalse(frappe.has_permission("AO Required Document", "read"))  # documents are off-limits
            with self.assertRaises(frappe.PermissionError):
                staff_api.reveal_intake(self.case_a)
        with as_user(self.finance):
            self.assertFalse(frappe.has_permission("AO Required Document", "read"))
            self.assertFalse(frappe.has_permission("AO Application Case", "write", doc=self.case_a))
            self.assertTrue(frappe.has_permission("Sales Invoice", "create"))
        with as_user(self.w1):
            self.assertFalse(frappe.has_permission("AO Settings", "write"))
            self.assertFalse(frappe.has_permission("Sales Invoice", "create"))
            with self.assertRaises(frappe.PermissionError):
                staff_api.create_invoice(self.case_a, "[]")
        with as_user(self.reviewer):
            self.assertTrue(frappe.has_permission("AO Required Document", "read", doc=self.rd_a))
            self.assertFalse(frappe.has_permission("AO Application Case", "create"))

    def test_sensitive_intake_masked_and_encrypted(self):
        raw = frappe.db.get_value("AO Application Case", self.case_a, "intake_data")
        self.assertNotIn("X1234567", raw)
        with as_user(self.w1):
            vals = {f["field_key"]: f["value"] for f in staff_api.masked_intake(self.case_a)}
            self.assertNotIn("X1234567", json.dumps(vals))
            n = frappe.db.count("AO Audit Event", {"action": "intake.revealed", "case": self.case_a})
            revealed = {f["field_key"]: f["value"] for f in staff_api.reveal_intake(self.case_a)}
            self.assertEqual(revealed["passport_number"], "X1234567")
            self.assertEqual(frappe.db.count("AO Audit Event", {"action": "intake.revealed", "case": self.case_a}), n + 1)
        with as_user(self.a):
            own = {f["field_key"]: f["value"] for f in portal_api.get_case(self.case_a)["intake"]}
            self.assertEqual(own["passport_number"], "X1234567")

    def test_portal_projection_has_no_internal_data(self):
        c = frappe.get_doc("AO Application Case", self.case_a)
        c.internal_notes = "SECRET-INTERNAL-NOTE"
        c.save(ignore_permissions=True)
        frappe.get_doc({"doctype": "AO Case Message", "case": self.case_a, "visibility": "Internal", "direction": "Staff",
                        "author": self.w1, "body": "INTERNAL-MSG"}).insert(ignore_permissions=True)
        rd = frappe.get_doc("AO Required Document", self.rd_a)
        frappe.db.set_value("AO Required Document", rd.name, "rejection_reason", "INTERNAL-REASON")
        with as_user(self.a):
            blob = json.dumps(portal_api.get_case(self.case_a), default=str)
        for secret in ("SECRET-INTERNAL-NOTE", "INTERNAL-MSG", "INTERNAL-REASON", self.w1):
            self.assertNotIn(secret, blob)

    def test_unpublished_program_cannot_be_started(self):
        p = make_program("Hidden Program", published=False)
        with as_user(self.a), self.assertRaises(frappe.DoesNotExistError):
            portal_api.start_case(p.name)
        with as_user(self.a):
            self.assertNotIn("Hidden Program", [s["program_name"] for s in portal_api.list_services()])
