"""Arabic-first localisation: defaults, switching, translation completeness, non-destructive branding."""
import glob
import json
import os
import re

import frappe
from frappe.tests import IntegrationTestCase

from application_office import install, localization, notifications, portal_strings
from application_office.workflow import CUSTOMER_STATUS_LABELS, status_label

AR = re.compile(r"[\u0600-\u06FF]")
# Terms that are intentionally identical in Arabic UI (product / technical identifiers)
KEEP = {"C1", "Sha256", "SHA-256", "DocuSeal", "AfaqBridge", "ClamAV", "Jinja", "IANA", "AO", "SUBMITTED", "READY_FOR_SUBMISSION"}
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestLocalization(IntegrationTestCase):
    def setUp(self):
        self._lang = frappe.local.lang

    def tearDown(self):
        frappe.local.lang = self._lang

    def test_normalise(self):
        self.assertEqual(localization.normalise("ar-SA"), "ar")
        self.assertEqual(localization.normalise("EN_us"), "en")
        self.assertIsNone(localization.normalise("fr"))
        self.assertIsNone(localization.normalise(""))

    def test_system_default_is_arabic_and_only_ar_en_enabled(self):
        self.assertEqual(frappe.db.get_single_value("System Settings", "language"), "ar")
        self.assertEqual(sorted(frappe.get_all("Language", {"enabled": 1}, pluck="name")), ["ar", "en"])
        self.assertEqual(frappe.db.get_single_value("Website Settings", "show_language_picker"), 1)

    def test_new_user_defaults_to_arabic_or_current_language(self):
        frappe.local.lang = "en"
        doc = frappe.new_doc("User"); localization.user_before_insert(doc)
        self.assertEqual(doc.language, "en")
        frappe.local.lang = "xx"
        doc = frappe.new_doc("User"); localization.user_before_insert(doc)
        self.assertEqual(doc.language, "ar")
        doc = frappe.new_doc("User"); doc.language = "en"; localization.user_before_insert(doc)
        self.assertEqual(doc.language, "en", "explicit choice must be kept")

    def test_set_language_rejects_unsupported(self):
        with self.assertRaises(frappe.ValidationError):
            localization.set_language("fr")

    def test_branding_applied_and_admin_edits_survive(self):
        self.assertEqual(frappe.db.get_single_value("Website Settings", "app_name"), "AfaqBridge")
        self.assertIn("afaqbridge", frappe.db.get_single_value("Website Settings", "app_logo"))
        frappe.db.set_single_value("Website Settings", "app_name", "Custom Brand")
        install.apply_branding_and_language(); install.apply_branding_and_language()  # idempotent
        self.assertEqual(frappe.db.get_single_value("Website Settings", "app_name"), "Custom Brand")
        frappe.db.set_single_value("Website Settings", "app_name", "AfaqBridge")
        items = [i.item_label for i in frappe.get_doc("Navbar Settings").settings_dropdown]
        self.assertEqual(items.count("العربية"), 1); self.assertEqual(items.count("English"), 1)

    def test_no_stale_brand_in_user_visible_defaults(self):
        self.assertEqual(frappe.get_hooks("app_title", app_name="application_office")[0], "AfaqBridge")
        self.assertNotIn("Application Office", json.dumps(portal_strings.portal_messages(), ensure_ascii=False))

    def test_portal_strings_all_translated(self):
        frappe.local.lang = "ar"
        bad = [k for k, v in portal_strings.portal_messages().items() if v == k and k not in KEEP and not k.startswith("{")]
        self.assertEqual(bad, [], "portal strings missing from locale/ar.po")

    def test_portal_js_uses_only_listed_strings(self):
        js = open(os.path.join(APP_DIR, "public/js/office_portal.js"), encoding="utf8").read()
        used = {json.loads(m.group(1)) for m in re.finditer(r'\b(?:t|tn|tx)\(("(?:[^"\\]|\\.)*")', js)}
        self.assertEqual(sorted(used - set(portal_strings.portal_messages())), [], "add to portal_strings.py")

    def test_doctype_labels_and_options_translated(self):
        frappe.local.lang = "ar"
        missing = set()
        for f in glob.glob(os.path.join(APP_DIR, "application_office/doctype/*/*.json")):
            d = json.load(open(f, encoding="utf8"))
            texts = [d["name"]] + [x.get("label") for x in d.get("fields", [])]
            for x in d.get("fields", []):
                if x.get("fieldtype") == "Select":
                    texts += [o.strip() for o in (x.get("options") or "").split("\n")]
            for t in filter(None, texts):
                if t not in KEEP and not AR.search(frappe._(t)):
                    missing.add(t)
        self.assertEqual(sorted(missing), [], "untranslated DocType strings")

    def test_status_labels_follow_language(self):
        for state in CUSTOMER_STATUS_LABELS:
            frappe.local.lang = "en"; en = status_label(state)
            frappe.local.lang = "ar"; ar = status_label(state)
            self.assertNotEqual(en, ar); self.assertTrue(AR.search(ar), state)

    def test_arabic_notification_templates_exist_and_render(self):
        for key in notifications._DEFAULT_BODY:
            name = f"{key}-ar"
            self.assertTrue(frappe.db.exists("AO Notification Template", name), name)
            body = frappe.db.get_value("AO Notification Template", name, "body")
            self.assertTrue(AR.search(body), name)
            frappe.render_template(body, {"customer_name": "Test", "case_reference": "AO-1", "program_name": "P",
                                          "status_label": "s", "deadline": "d", "portal_url": "u", "message": "m",
                                          "office_name": "o", "disclaimer": "x", "set_password_url": ""})

    def test_default_disclaimer_translates_until_edited(self):
        frappe.local.lang = "ar"
        self.assertTrue(AR.search(localization.translate_if_default(install.DEFAULT_DISCLAIMER, install.DEFAULT_DISCLAIMER)))
        self.assertEqual(localization.translate_if_default("<p>Custom text</p>", install.DEFAULT_DISCLAIMER), "Custom text")
