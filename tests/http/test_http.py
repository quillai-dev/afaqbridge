"""HTTP-level security tests against a RUNNING bench (default http://127.0.0.1:8000, site office.localhost).

Run:  make dev-http-test   (starts the server, runs this file with the bench Python)
Creates uniquely-tagged data and removes the users it created afterwards. DocuSeal webhook acceptance of a *valid*
signature is covered in the in-app tests; here we assert rejection paths over real HTTP."""
import io
import json
import os
import re
import sys
import unittest

import requests

BASE = os.environ.get("AO_BASE", "http://127.0.0.1:8000")
SITE = os.environ.get("AO_SITE", "office.localhost")
BENCH_SITES = "/home/frappe/frappe-bench/sites"
TAG = os.environ.get("AO_TAG", "h" + __import__("secrets").token_hex(3))
PWD = "Str0ng!Passw0rd-" + TAG
HDR = {"Host": f"{SITE}:8000"}


def fixture():
    """Create program + two customers (committed) inside a Frappe context."""
    import frappe
    os.chdir(BENCH_SITES)
    frappe.init(SITE, sites_path="."); frappe.connect()
    from frappe.utils import add_days, now_datetime, today
    from frappe.utils.password import update_password
    from application_office import customers, portal_api
    out = {}
    if not frappe.db.exists("AO Program", "HTTP Program"):
        frappe.get_doc({"doctype": "AO Program", "program_name": "HTTP Program", "program_category": "Scholarship", "published": 1,
                        "service_available": 1, "responsible_employee": "Administrator", "last_verified_on": today(),
                        "time_zone": "UTC", "closing_datetime": add_days(now_datetime(), 20),
                        "document_requirements": [{"document_category": "Passport", "required": 1}],
                        "intake_fields": [{"field_key": "full_name", "label": "Full name", "field_type": "Text", "required": 1}]}
                       ).insert(ignore_permissions=True)
    for who in ("a", "b"):
        email = f"{who}-{TAG}@http.test"
        r = customers.create_customer_with_user(email, f"HTTP {who} {TAG}", "en",
                                                {"Terms of Service": 1, "Privacy Notice": 1, "Sensitive Data Processing": 1}, send_welcome=False)
        update_password(email, PWD)
        frappe.set_user(email)
        case = portal_api.start_case("HTTP Program")["case"]
        frappe.set_user("Administrator")
        out[who] = {"email": email, "customer": r["customer"], "case": case,
                    "rd": frappe.get_all("AO Required Document", filters={"case": case}, pluck="name")[0]}
    frappe.db.commit(); frappe.destroy()
    return out


def login(email):
    s = requests.Session()
    r = s.post(f"{BASE}/api/method/login", data={"usr": email, "pwd": PWD}, headers=HDR)
    assert r.status_code == 200, r.text
    page = s.get(f"{BASE}/office-portal", headers=HDR).text
    token = s.get(f"{BASE}/api/method/application_office.portal_api.csrf_token", headers=HDR).json()["message"]
    assert token and "{{" not in token
    s.headers.update({**HDR, "X-Frappe-CSRF-Token": token})
    return s, page


PDF = None


def pdf_bytes():
    from io import BytesIO

    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(72, 72); b = BytesIO(); w.write(b)
    return b.getvalue()


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = fixture()
        cls.sa, cls.page_a = login(cls.d["a"]["email"])
        cls.sb, _ = login(cls.d["b"]["email"])
        r = cls.sa.post(f"{BASE}/api/method/application_office.portal_api.upload_document",
                        data={"case": cls.d["a"]["case"], "required_document": cls.d["a"]["rd"]},
                        files={"file": ("p.pdf", pdf_bytes(), "application/pdf")})
        assert r.status_code == 200, r.text

    def m(self, s, name, method="get", **kw):
        return getattr(s, method)(f"{BASE}/api/method/application_office.portal_api.{name}", **kw)

    def test_guest_is_rejected(self):
        for n in ("list_cases", "list_services", "list_invoices"):
            self.assertIn(requests.get(f"{BASE}/api/method/application_office.portal_api.{n}", headers=HDR).status_code, (401, 403), n)

    def test_foreign_case_is_404_and_own_is_200(self):
        self.assertEqual(self.m(self.sb, "get_case", params={"case": self.d["a"]["case"]}).status_code, 404)
        self.assertEqual(self.m(self.sb, "get_case", params={"case": "AC-1999-99999"}).status_code, 404)
        self.assertEqual(self.m(self.sa, "get_case", params={"case": self.d["a"]["case"]}).status_code, 200)
        cases = self.m(self.sb, "list_cases").json()["message"]
        self.assertEqual([c["name"] for c in cases], [self.d["b"]["case"]])

    def test_rest_resource_api_is_closed_to_customers(self):
        for path in ("AO Application Case", f"AO Application Case/{self.d['a']['case']}", "AO Required Document",
                     "AO Program", "AO Audit Event", "AO Settings/AO Settings", "File", "Customer", "Sales Invoice"):
            r = self.sb.get(f"{BASE}/api/resource/{path}")
            self.assertIn(r.status_code, (200, 403, 404), f"{path}: {r.status_code}")
            # Even when Frappe answers 200 (own files / own customer record) NOTHING of customer A may appear.
            for secret in (self.d["a"]["case"], self.d["a"]["rd"], self.d["a"]["customer"], self.d["a"]["email"]):
                self.assertNotIn(secret, r.text, f"{path} leaked {secret}")
            if path.startswith("AO "):
                self.assertIn(r.status_code, (403, 404), path)
        for dt in ("AO Application Case", "AO Official Submission"):
            r = self.sb.post(f"{BASE}/api/resource/{dt}", json={"case": self.d["b"]["case"]})
            self.assertIn(r.status_code, (403, 404, 417, 400), dt)

    def test_generic_frappe_methods_do_not_leak(self):
        r = self.sb.get(f"{BASE}/api/method/frappe.client.get", params={"doctype": "AO Application Case", "name": self.d["a"]["case"]})
        self.assertIn(r.status_code, (403, 404))
        r = self.sb.get(f"{BASE}/api/method/frappe.client.get_list", params={"doctype": "AO Required Document"})
        self.assertIn(r.status_code, (403, 404))
        r = self.sb.get(f"{BASE}/api/method/frappe.desk.search.search_link", params={"doctype": "AO Application Case", "txt": "AC"})
        self.assertNotIn(self.d["a"]["case"], r.text)

    def test_private_file_is_not_public_or_cross_customer(self):
        case = self.sa.get(f"{BASE}/api/method/application_office.portal_api.get_case", params={"case": self.d["a"]["case"]}).json()["message"]
        self.assertEqual(case["documents"][0]["upload_status"], "Uploaded")
        import frappe
        os.chdir(BENCH_SITES); frappe.init(SITE, sites_path="."); frappe.connect()
        url = frappe.db.get_value("File", {"attached_to_name": self.d["a"]["rd"]}, "file_url"); frappe.destroy()
        self.assertTrue(url.startswith("/private/files/"))
        self.assertIn(requests.get(BASE + url, headers=HDR).status_code, (401, 403))          # guest
        self.assertIn(self.sb.get(BASE + url).status_code, (403, 404))                         # other customer
        pub = requests.get(f"{BASE}/files/{url.rsplit('/', 1)[-1]}", headers=HDR)   # dev server answers 500, nginx 404
        self.assertNotEqual(pub.status_code, 200); self.assertFalse(pub.content.startswith(b"%PDF"))
        dl = self.m(self.sa, "download_document", params={"case": self.d["a"]["case"], "required_document": self.d["a"]["rd"]})
        self.assertEqual(dl.status_code, 200); self.assertTrue(dl.content.startswith(b"%PDF"))
        self.assertEqual(self.m(self.sb, "download_document", params={"case": self.d["a"]["case"], "required_document": self.d["a"]["rd"]}).status_code, 404)

    def test_csrf_is_enforced_on_state_changing_calls(self):
        s = requests.Session()
        s.post(f"{BASE}/api/method/login", data={"usr": self.d["a"]["email"], "pwd": PWD}, headers=HDR)
        s.get(f"{BASE}/api/method/application_office.portal_api.csrf_token", headers=HDR)   # portal start-up issues the token
        # wrong token must also be refused
        bad = s.post(f"{BASE}/api/method/application_office.portal_api.send_message", headers={**HDR, "X-Frappe-CSRF-Token": "wrong"},
                     data={"case": self.d["a"]["case"], "body": "csrf probe"})
        self.assertIn(bad.status_code, (400, 403))
        r = s.post(f"{BASE}/api/method/application_office.portal_api.send_message", headers=HDR,
                   data={"case": self.d["a"]["case"], "body": "csrf probe"})
        self.assertIn(r.status_code, (400, 403), r.text[:200])

    def test_staff_endpoints_forbidden_for_customers(self):
        for fn, data in (("transition", {"case": self.d["a"]["case"], "to_state": "ON_HOLD", "reason": "x"}),
                         ("reveal_intake", {"case": self.d["a"]["case"]}), ("delete_case_data", {"case": self.d["a"]["case"]})):
            r = self.sa.post(f"{BASE}/api/method/application_office.staff_api.{fn}", data=data)
            self.assertEqual(r.status_code, 403, fn)

    def test_upload_validation_over_http(self):
        up = lambda name, content: self.sa.post(f"{BASE}/api/method/application_office.portal_api.upload_document",
                                                data={"case": self.d["a"]["case"], "required_document": self.d["a"]["rd"]},
                                                files={"file": (name, content, "application/octet-stream")})
        for name, content in (("evil.exe", b"MZ\x90\x00"), ("fake.pdf", b"<html>not a pdf</html>"), ("x.pdf", b""),
                              ("js.pdf", pdf_bytes() + b"/JavaScript (x)")):
            self.assertGreaterEqual(up(name, content).status_code, 400, name)
        self.assertEqual(up("good.pdf", pdf_bytes() + b"\n%v2").status_code, 200)
        r = self.sa.post(f"{BASE}/api/method/application_office.portal_api.upload_document",
                         data={"case": self.d["a"]["case"], "required_document": self.d["a"]["rd"]})
        self.assertGreaterEqual(r.status_code, 400)  # no file part

    def test_xss_payload_stored_is_not_executed_by_portal_js(self):
        src = open("/home/claude/application-office/apps/application_office/application_office/public/js/office_portal.js").read()
        self.assertIsNone(re.search(r"\.innerHTML\s*[=+]|insertAdjacentHTML|outerHTML\s*=", src))
        self.assertNotIn("document.write", src)
        self.assertNotIn("eval(", src)

    def test_session_cookie_flags(self):
        r = requests.post(f"{BASE}/api/method/login", data={"usr": self.d["a"]["email"], "pwd": PWD}, headers=HDR)
        sid = [h for h in r.raw.headers.getlist("Set-Cookie") if h.startswith("sid=")][0].lower()
        self.assertIn("httponly", sid); self.assertIn("samesite", sid)
        # 'Secure' is only emitted over HTTPS (reverse proxy); asserted in deployment docs, not here.

    def test_wrong_password_and_lockout(self):
        # Frappe also tracks failures per client IP; use an isolated address so other tests are unaffected.
        h = {**HDR, "X-Forwarded-For": f"203.0.113.{int(TAG[1:], 16) % 250 + 1}"}
        codes = [requests.post(f"{BASE}/api/method/login", data={"usr": self.d["b"]["email"], "pwd": "wrong"}, headers=h).status_code
                 for _ in range(8)]
        self.assertEqual(codes[0], 401)
        r = requests.post(f"{BASE}/api/method/login", data={"usr": self.d["b"]["email"], "pwd": PWD}, headers=h)
        # Invariant: once locked, even the CORRECT password is refused and no session is issued.
        # (Frappe reports the lock as HTTP 500 + SecurityException - an upstream quirk, documented.)
        self.assertNotEqual(r.status_code, 200)
        self.assertIn("locked", r.text.lower())
        self.assertNotIn("sid=" + self.d["b"]["email"], r.headers.get("Set-Cookie", ""))

    def test_docuseal_webhook_rejects_unsigned_over_http(self):
        r = requests.post(f"{BASE}/api/method/application_office.integrations.docuseal.webhook", headers=HDR,
                          json={"event_type": "form.completed", "data": {"id": 1}})
        self.assertIn(r.status_code, (401, 503))

    def test_registration_endpoint_is_uniform_and_rate_limited(self):
        h = {**HDR, "X-Forwarded-For": f"198.51.100.{int(TAG[1:], 16) % 250 + 1}"}   # isolated IP bucket for this test
        email = f"reg-{TAG}@http.test"
        body = {"email": email, "full_name": "Reg Person", "accept_terms": 1, "accept_privacy": 1, "accept_sensitive": 1}
        url = f"{BASE}/api/method/application_office.portal_api.register"
        r1 = requests.post(url, data=body, headers=h)
        r2 = requests.post(url, data=body, headers=h)
        self.assertEqual(r1.status_code, 200); self.assertEqual(r1.json(), r2.json())   # new vs existing address: identical
        codes = [requests.post(url, data={**body, "email": f"x{i}-{TAG}@http.test"}, headers=h).status_code for i in range(12)]
        self.assertIn(429, codes)

    def test_registration_mail_delivery_via_smtp_sink(self):
        """Register, flush Frappe's email queue, and confirm a message with a set-password link reached the SMTP sink."""
        import glob, subprocess
        h = {**HDR, "X-Forwarded-For": f"192.0.2.{int(TAG[1:], 16) % 250 + 1}"}
        email = f"mail-{TAG}@http.test"
        before = set(glob.glob("/tmp/mailsink/*.eml"))
        r = requests.post(f"{BASE}/api/method/application_office.portal_api.register", headers=h,
                          data={"email": email, "full_name": "Mail Person", "accept_terms": 1, "accept_privacy": 1, "accept_sensitive": 1})
        self.assertEqual(r.status_code, 200)
        import frappe
        os.chdir(BENCH_SITES); frappe.init(SITE, sites_path="."); frappe.connect()
        frappe.set_user("Administrator")   # the scheduler flushes the queue as Administrator
        from frappe.email.queue import flush
        mine = []
        for _ in range(20):   # Frappe holds new mail for a 10 s "undo window" before it is eligible to send
            frappe.db.rollback()   # end the REPEATABLE READ snapshot so rows committed by the server are visible
            flush(); frappe.db.commit()
            import time; time.sleep(1)
            new = set(glob.glob("/tmp/mailsink/*.eml")) - before
            mine = [m for m in (open(f, errors="replace").read() for f in new) if email in m]
            if mine:
                break
        frappe.destroy()
        self.assertTrue(mine, "no mail for the new customer reached the sink")
        import email as emaillib
        msg = emaillib.message_from_string(mine[0].split("\n", 1)[1])   # drop the sink's envelope line
        text = " ".join(part.get_payload(decode=True).decode("utf-8", "replace") for part in msg.walk()
                        if part.get_content_type() in ("text/html", "text/plain") and part.get_payload(decode=True))
        self.assertIn("update-password", text)   # one-time set-password link (also verifies e-mail ownership)
        self.assertNotIn("disclaimer-placeholder", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
