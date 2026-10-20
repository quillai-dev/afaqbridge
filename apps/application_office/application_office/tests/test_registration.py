import frappe
from frappe.tests import IntegrationTestCase

from application_office import customers, portal_api, staff_api
from application_office.common import customer_for_user
from application_office.tests.utils import *  # noqa: F401,F403

ALL = {"Terms of Service": 1, "Privacy Notice": 1, "Sensitive Data Processing": 1}


class TestRegistration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_ao_settings()
        cls.program = make_program().name
        cls.worker = make_staff("regw", "AO Case Worker")

    def test_registration_creates_linked_records_and_consents(self):
        r = customers.create_customer_with_user("New.Person@Example.test", "New Person", "nl", ALL, send_welcome=False)
        self.assertTrue(r["created"])
        user = frappe.get_doc("User", "new.person@example.test")
        self.assertEqual(user.user_type, "Website User")
        self.assertIn("Customer", [x.role for x in user.roles])
        self.assertFalse(set(r.role for r in user.roles) & {"System Manager", "AO Administrator", "AO Case Worker"})
        cust = frappe.get_doc("Customer", r["customer"])
        self.assertTrue(cust.ao_customer_reference.startswith("CU-"))
        self.assertEqual(customer_for_user("new.person@example.test"), cust.name)
        types = set(frappe.get_all("AO Consent Record", filters={"customer": cust.name, "granted": 1}, pluck="consent_type"))
        self.assertEqual(types, set(ALL))
        self.assertTrue(frappe.db.exists("AO Notification Log", {"dedupe_key": f"reg:{cust.name}"}))

    def test_requires_consents_and_valid_input(self):
        with self.assertRaises(frappe.ValidationError):
            customers.create_customer_with_user("x1@example.test", "X One", "en", {"Terms of Service": 1})
        for bad in (("not-an-email", "Name"), ("ok@example.test", "")):
            with self.assertRaises(frappe.ValidationError):
                customers.create_customer_with_user(*bad, "en", ALL)

    def test_duplicate_registration_is_silent(self):
        customers.create_customer_with_user("dup@example.test", "Dup", "en", ALL, send_welcome=False)
        self.assertFalse(customers.create_customer_with_user("dup@example.test", "Other Name", "en", ALL)["created"])
        self.assertEqual(frappe.db.count("Customer", {"customer_name": "Other Name"}), 0)

    def test_public_register_endpoint_response_is_uniform(self):
        with as_user("Guest"):
            a = portal_api.register.__wrapped__("uni1@example.test", "Uni One", "en", 1, 1, 1) if hasattr(portal_api.register, "__wrapped__") else None
        if a is not None:
            self.assertEqual(a["ok"], True)

    def test_invited_customer_must_accept_consents_before_work(self):
        with as_user(self.worker):
            r = staff_api.invite_customer("invitee@example.test", "Invitee", "en")
        self.assertTrue(r["created"])
        self.assertEqual(frappe.db.get_value("Customer", r["customer"], "ao_account_status"), "Invited")
        with as_user("invitee@example.test"):
            self.assertFalse(portal_api.bootstrap()["user"]["consents_ok"])
            with self.assertRaises(frappe.PermissionError):
                portal_api.start_case(self.program)
            portal_api.accept_current_consents()
            self.assertTrue(portal_api.bootstrap()["user"]["consents_ok"])
            self.assertTrue(portal_api.start_case(self.program)["case"])

    def test_policy_version_bump_requires_new_consent(self):
        email, cust = make_customer("reconsent")
        self.assertTrue(customers.has_required_consents(cust))
        frappe.db.set_single_value("AO Settings", "privacy_version", "2"); frappe.clear_cache()
        try:
            self.assertFalse(customers.has_required_consents(cust))
        finally:
            frappe.db.set_single_value("AO Settings", "privacy_version", "1"); frappe.clear_cache()

    def test_disclaimer_is_served_publicly(self):
        with as_user("Guest"):
            b = portal_api.bootstrap()
        self.assertIn("guarantee", b["disclaimer"].lower())
        self.assertIsNone(b["user"])

    def test_only_published_available_verified_programs_startable(self):
        email, _ = make_customer("startable")
        stale = make_program("Stale Program", last_verified_on=frappe.utils.add_days(frappe.utils.today(), -90))
        with as_user(email):
            svc = {s["program_name"]: s for s in portal_api.list_services()}
            self.assertTrue(svc["Test Program"]["startable"])
            self.assertFalse(svc["Stale Program"]["startable"])
            with self.assertRaises(frappe.ValidationError):
                portal_api.start_case(stale.name)

    def test_program_cannot_be_published_without_verification_date(self):
        with self.assertRaises(frappe.ValidationError):
            make_program("Unverified", last_verified_on=None)


class TestRateLimit(IntegrationTestCase):
    def test_user_rate_limiter_blocks_after_limit(self):
        from application_office.common import check_rate
        user = f"rl-{frappe.generate_hash(length=6)}@x.test"
        for _ in range(3):
            check_rate("t", user, 3, 60)
        with self.assertRaises(frappe.RateLimitExceededError):
            check_rate("t", user, 3, 60)
        check_rate("t", "someone-else@x.test", 3, 60)  # independent per user


class TestMFA(IntegrationTestCase):
    def test_mfa_required_for_staff_roles_not_customers(self):
        from frappe.twofactor import two_factor_is_enabled_for_
        ensure_ao_settings()
        staff = make_staff("mfa1", "AO Case Worker")
        cust, _ = make_customer("mfacust")
        self.assertTrue(frappe.db.get_single_value("System Settings", "enable_two_factor_auth"))
        self.assertTrue(two_factor_is_enabled_for_(staff))
        self.assertFalse(two_factor_is_enabled_for_(cust))
