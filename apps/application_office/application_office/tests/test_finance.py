import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from application_office import portal_api, scheduler, staff_api
from application_office.tests.utils import *  # noqa: F401,F403


class TestFinance(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_ao_settings()
        cls.fin = make_staff("finx", "AO Finance", "Accounts User")
        cls.worker = make_staff("finw", "AO Case Worker")
        cls.a, cls.a_cust = make_customer("fina")
        cls.b, cls.b_cust = make_customer("finb")
        cls.program = make_program().name
        cls.case = start_case_for(cls.a, cls.program)

    def _invoice(self, due=None):
        with as_user(self.fin):
            r = staff_api.create_invoice(self.case, json.dumps([{"description": "Application assistance", "rate": 100, "qty": 1},
                                                                 {"description": "Translation", "rate": 25.5, "qty": 2}]))
        inv = frappe.get_doc("Sales Invoice", r["invoice"])
        self.assertEqual(inv.docstatus, 0)
        self.assertEqual(inv.ao_application_case, self.case)
        self.assertEqual(inv.customer, self.a_cust)
        self.assertEqual(round(inv.grand_total, 2), 151.0)
        self.assertEqual(inv.currency, frappe.db.get_value("Company", inv.company, "default_currency"))  # nothing hard-coded
        if due:
            inv.due_date = due
        inv.posting_date = add_days(today(), -120) if due else today()
        inv.set_posting_time = 1
        with as_user(self.fin):
            inv.submit()
        if due:  # ERPNext recomputes due dates from payment terms; force the overdue scenario directly
            frappe.db.set_value("Sales Invoice", inv.name, "due_date", due)
        return inv

    def test_invoice_lifecycle_and_portal_visibility(self):
        inv = self._invoice()
        self.assertEqual(inv.status, "Unpaid")
        with as_user(self.a):
            names = [i["name"] for i in portal_api.list_invoices()]
            self.assertIn(inv.name, names)
            self.assertIn(inv.name, [i["name"] for i in portal_api.get_case(self.case)["invoices"]])
        with as_user(self.b):
            self.assertNotIn(inv.name, [i["name"] for i in portal_api.list_invoices()])
        # payment through ERPNext Payment Entry -> status becomes Paid
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
        with as_user(self.fin):
            pe = get_payment_entry("Sales Invoice", inv.name)
            pe.reference_no, pe.reference_date = "BANK-1", today()
            pe.insert(); pe.submit()
        inv.reload()
        self.assertEqual((inv.status, inv.outstanding_amount), ("Paid", 0))
        with as_user(self.a):
            row = [i for i in portal_api.list_invoices() if i["name"] == inv.name][0]
        self.assertEqual(row["status"], "Paid")
        # cancellation (refund records live in ERPNext credit notes / payment entries)
        with as_user(self.fin):
            pe.cancel()
            inv.reload(); inv.cancel()
        self.assertEqual(frappe.db.get_value("Sales Invoice", inv.name, "status"), "Cancelled")

    def test_only_finance_or_admin_create_invoices(self):
        with as_user(self.worker), self.assertRaises(frappe.PermissionError):
            staff_api.create_invoice(self.case, json.dumps([{"description": "x", "rate": 1}]))
        with as_user(self.fin), self.assertRaises(frappe.ValidationError):
            staff_api.create_invoice(self.case, "[]")

    def test_overdue_invoice_reminder_sent_once(self):
        inv = self._invoice(due=add_days(today(), -30))
        key = f"inv:{inv.name}:overdue"
        scheduler.send_invoice_reminders(); scheduler.send_invoice_reminders()
        self.assertEqual(frappe.db.count("AO Notification Log", {"dedupe_key": key}), 1)
