from datetime import datetime, timedelta, timezone

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime

from application_office import notifications, scheduler, staff_api
from application_office.tests.utils import *  # noqa: F401,F403


class TestNotifications(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_ao_settings()
        cls.reviewer = make_staff("nrev", "AO Reviewer")
        cls.cust, cls.cust_name = make_customer("notif")
        cls.program = make_program().name

    def test_dedupe(self):
        a = notifications.send("missing_documents", self.cust_name, "dd:1")
        b = notifications.send("missing_documents", self.cust_name, "dd:1")
        self.assertIsNotNone(a); self.assertIsNone(b)
        self.assertEqual(frappe.db.count("AO Notification Log", {"dedupe_key": "dd:1"}), 1)
        self.assertEqual(frappe.db.count("Email Queue", {"reference_name": a.name}), 1)

    def test_disabled_template_is_skipped_and_logged(self):
        frappe.db.set_value("AO Notification Template", "case_closed-en", "enabled", 0)
        try:
            self.assertIsNone(notifications.send("case_closed", self.cust_name, "dis:1"))
            self.assertEqual(frappe.db.get_value("AO Notification Log", {"dedupe_key": "dis:1"}, "status"), "Skipped")
        finally:
            frappe.db.set_value("AO Notification Template", "case_closed-en", "enabled", 1)

    def test_internal_notes_never_in_email(self):
        case = start_case_for(self.cust, self.program)
        frappe.db.set_value("AO Application Case", case, "internal_notes", "TOPSECRET-NOTE")
        fill_intake(self.cust, case); upload_all(case, self.cust); customer_submit(case, self.cust)
        rd = frappe.get_all("AO Required Document", filters={"case": case}, pluck="name")[0]
        with as_user(self.reviewer):
            staff_api.review_document(rd, "Correction Required", "INTERNAL-FINDING", "Rescan please", "Rescan please")
        mails = frappe.get_all("Email Queue", filters={"reference_doctype": "AO Notification Log"}, fields=["message"])
        text = " ".join(m.message for m in mails)
        self.assertIn("Rescan please", text)
        self.assertNotIn("TOPSECRET-NOTE", text)
        self.assertNotIn("INTERNAL-FINDING", text)

    def test_deadline_reminders_use_program_timezone_and_fire_once(self):
        case = start_case_for(self.cust, self.program)
        # Deadline 2026-12-31 23:00 in Europe/Berlin == 22:00 UTC
        frappe.db.set_value("AO Application Case", case, "applicable_deadline", "2026-12-31 23:00:00")
        self.assertEqual(scheduler.deadline_utc("2026-12-31 23:00:00", "Europe/Berlin").hour, 22)
        far = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.assertEqual([x for x in scheduler.send_deadline_reminders(far) if x.startswith(case)], [])
        near = datetime(2026, 12, 29, 12, 0, tzinfo=timezone.utc)   # ~2.4 days left -> 3-day threshold
        self.assertEqual([x for x in scheduler.send_deadline_reminders(near) if x.startswith(case)], [f"{case}:3"])
        self.assertEqual([x for x in scheduler.send_deadline_reminders(near) if x.startswith(case)], [])  # no duplicate
        later = datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc)  # 10h left -> 1-day threshold
        self.assertEqual([x for x in scheduler.send_deadline_reminders(later) if x.startswith(case)], [f"{case}:1"])
        past = datetime(2027, 1, 2, tzinfo=timezone.utc)
        self.assertEqual([x for x in scheduler.send_deadline_reminders(past) if x.startswith(case)], [])
        msg = frappe.get_all("Email Queue", filters={"reference_doctype": "AO Notification Log"}, fields=["message"], order_by="creation desc", limit=1)[0].message
        self.assertIn("2026-12-31 23:00 CET", msg)

    def test_closed_case_gets_no_deadline_reminder(self):
        case = start_case_for(self.cust, self.program)
        frappe.db.set_value("AO Application Case", case, {"applicable_deadline": "2026-12-31 23:00:00", "case_state": "CANCELLED"})
        near = datetime(2026, 12, 30, tzinfo=timezone.utc)
        self.assertEqual([x for x in scheduler.send_deadline_reminders(near) if x.startswith(case)], [])

    def test_delivery_status_sync(self):
        log = notifications.send("case_closed", self.cust_name, "sync:1")
        q = frappe.db.get_value("AO Notification Log", log.name, "email_queue")
        frappe.db.set_value("Email Queue", q, "status", "Sent")
        notifications.refresh_delivery_status()
        self.assertEqual(frappe.db.get_value("AO Notification Log", log.name, "status"), "Sent")

    def test_template_render_failure_is_logged_not_raised(self):
        frappe.db.set_value("AO Notification Template", "case_closed-en", "body", "{{ 1/0 }}")
        try:
            log = notifications.send("case_closed", self.cust_name, "bad:1")
            self.assertEqual(frappe.db.get_value("AO Notification Log", log.name, "status"), "Error")
        finally:
            frappe.db.set_value("AO Notification Template", "case_closed-en", "body", "<p>Case {{ case_reference }} closed</p>")
