"""DocuSeal integration tests.

DISCLOSURE: DocuSeal itself is NOT running in this environment (no Docker / Ruby 3.4 stack). These tests run
against `SimulatedDocuSeal`, a small HTTP server that mimics ONLY the endpoints and payload shapes verified in the
upstream 3.3.2 source (POST /api/submissions, GET /api/submissions/:id/documents, X-Auth-Token auth, HMAC webhook
signature). They prove OUR side of the contract; they do not prove a real DocuSeal instance behaves identically."""
import inspect
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from application_office import portal_api, staff_api
from application_office.integrations import docuseal
from application_office.tests.utils import *  # noqa: F401,F403
from application_office.tests.utils import PDF

SECRET = "whsec_unit-test-secret"
TOKEN = "ds-api-token"


class SimulatedDocuSeal:
    def __init__(self):
        self.fail = False
        self.counter = 0
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code); self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                outer.requests.append(("POST", self.path, dict(self.headers), body))
                if self.headers.get("X-Auth-Token") != TOKEN:
                    return self._send(401, {"error": "Not authorized"})
                if outer.fail:
                    return self._send(500, {"error": "boom"})
                s = body["submitters"][0]
                outer.counter += 1
                self._send(200, [{"id": 501, "submission_id": 900 + outer.counter, "slug": "abc", "email": s["email"],
                                  "external_id": s.get("external_id"), "status": "awaiting",
                                  "embed_src": f"http://127.0.0.1:{outer.port}/s/abc"}])

            def do_GET(self):
                outer.requests.append(("GET", self.path, dict(self.headers), None))
                if self.path.startswith("/files/"):
                    return self._send(200, PDF, "application/pdf")
                if self.headers.get("X-Auth-Token") != TOKEN:
                    return self._send(401, {"error": "Not authorized"})
                self._send(200, {"documents": [{"name": "signed", "url": f"http://127.0.0.1:{outer.port}/files/signed.pdf"}]})

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()


def set_request(body: bytes, header: str | None):
    headers = {"Content-Type": "application/json"}
    if header is not None:
        headers["X-Docuseal-Signature"] = header
    frappe.local.request = Request(EnvironBuilder(method="POST", data=body, headers=headers).get_environ())


def call_webhook(payload: dict, header="auto", secret=SECRET, ts=None):
    body = json.dumps(payload).encode()
    if header == "auto":
        header = docuseal.sign(secret, body, ts)
    set_request(body, header)
    fn = inspect.unwrap(docuseal.webhook)
    out = fn()
    return frappe.local.response.get("http_status_code", 200), out["message"]


def event(event_type, submitter_id, external_id, stamp="2026-10-19T10:00:00Z", submission_id=900):
    return {"event_type": event_type, "timestamp": stamp,
            "data": {"id": submitter_id, "submission_id": submission_id, "external_id": external_id, "status": "completed",
                     "submission": {"id": submission_id}}}


class TestDocuSeal(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_ao_settings()
        cls.sim = SimulatedDocuSeal()
        s = frappe.get_doc("AO Settings")
        s.docuseal_enabled = 1
        s.docuseal_base_url = f"http://127.0.0.1:{cls.sim.port}"
        s.docuseal_api_token = TOKEN
        s.docuseal_webhook_secret = SECRET
        s.save(ignore_permissions=True)
        cls.worker = make_staff("dsw", "AO Case Worker")
        cls.reviewer = make_staff("dsr", "AO Reviewer")
        cls.program = make_program("Signed Program", form_templates=[
            {"form_name": "Application form", "docuseal_template_id": "7", "signature_required": 1}]).name

    @classmethod
    def tearDownClass(cls):
        cls.sim.stop()
        super().tearDownClass()

    def _case_waiting_for_signature(self, tag):
        cust, _ = make_customer(tag)
        case = drive_to_ready_for_submission(self.program, cust, self.worker, self.reviewer)
        return cust, case

    # ---- signature primitive (mirrors DocuSeal's WebhookUrls::Signatures)
    def test_signature_verification(self):
        body = b'{"a":1}'
        now = 1_800_000_000
        good = docuseal.sign(SECRET, body, now)
        self.assertTrue(docuseal.verify_signature(SECRET, body, good, now=now + 10))
        for bad, kw in ((docuseal.sign("whsec_other", body, now), {}), (good, {"body": b'{"a":2}'}),
                        (docuseal.sign(SECRET, body, now - 301), {}), (docuseal.sign(SECRET, body, now + 301), {}),
                        ("garbage", {}), (None, {}), ("123.", {}), ("abc.def", {})):
            with self.assertRaises(docuseal.SignatureError, msg=str(bad)):
                docuseal.verify_signature(SECRET, kw.get("body", body), bad, now=now)
        with self.assertRaises(docuseal.SignatureError):
            docuseal.verify_signature("", body, good, now=now)

    # ---- full signing flow
    def test_signing_flow_end_to_end(self):
        cust, case = self._case_waiting_for_signature("ds1")
        # approval happened but signature pending -> must NOT be READY_FOR_SUBMISSION
        self.assertEqual(frappe.db.get_value("AO Application Case", case, "case_state"), "READY_FOR_CUSTOMER_APPROVAL")
        self.assertEqual(frappe.db.get_value("AO Application Case", case, "final_customer_approval_status"), "Approved")
        fa = frappe.get_all("AO Form Approval", filters={"case": case}, pluck="name")[0]
        with as_user(cust):
            url = portal_api.get_signing_url(case, fa)["url"]
            self.assertEqual(portal_api.get_signing_url(case, fa)["url"], url)  # idempotent: one DocuSeal submission
        self.assertEqual(len([r for r in self.sim.requests if r[0] == "POST" and r[3] and r[3].get("external_id") is None
                              and r[3]["submitters"][0]["external_id"] == fa]), 1)
        posted = [r for r in self.sim.requests if r[0] == "POST"][-1]
        self.assertEqual(posted[3]["template_id"], 7)
        self.assertIs(posted[3]["send_email"], False)
        self.assertEqual(posted[2].get("X-Auth-Token"), TOKEN)
        row = frappe.get_doc("AO Form Approval", fa)
        self.assertEqual((row.submission_status, row.signature_status), ("Sent", "Pending"))
        self.assertTrue(row.docuseal_submission_id.isdigit())
        # guard: staff can't move to READY_FOR_SUBMISSION while signature outstanding
        ev = event("form.completed", 501, fa, submission_id=int(row.docuseal_submission_id))
        code, msg = call_webhook(ev)
        self.assertEqual((code, msg), (200, "accepted"))
        e = frappe.get_doc("AO Integration Event", {"event_key": "docuseal:form.completed:501:2026-10-19T10:00:00Z"})
        if e.status == "Received":   # queue executes inline in tests; if not, run it explicitly
            docuseal.process_event(e.name); e.reload()
        self.assertEqual(e.status, "Processed")
        row.reload()
        self.assertEqual((row.signature_status, row.submission_status, row.customer_approval), ("Signed", "Completed", 1))
        self.assertTrue(row.signed_document_file)
        self.assertEqual(frappe.db.get_value("File", row.signed_document_file, "is_private"), 1)
        self.assertEqual(frappe.db.get_value("AO Application Case", case, "case_state"), "READY_FOR_SUBMISSION")
        # duplicate delivery (DocuSeal retries) is acknowledged but not reprocessed
        n = frappe.db.count("AO Audit Event", {"action": "docuseal.completed", "case": case})
        self.assertEqual(call_webhook(ev), (200, "duplicate"))
        self.assertEqual(frappe.db.count("AO Audit Event", {"action": "docuseal.completed", "case": case}), n)
        # a late 'viewed' event can never downgrade a completed signature
        call_webhook(event("form.viewed", 501, fa, "2026-10-19T11:00:00Z", int(row.docuseal_submission_id)))
        self.assertEqual(frappe.db.get_value("AO Form Approval", fa, "submission_status"), "Completed")

    def test_webhook_rejects_bad_signature_replay_and_garbage(self):
        n0 = frappe.db.count("AO Integration Event")
        ev = event("form.completed", 777, "NONEXISTENT", submission_id=424242)
        self.assertEqual(call_webhook(ev, header=None)[0], 401)
        self.assertEqual(call_webhook(ev, header="12.abc")[0], 401)
        self.assertEqual(call_webhook(ev, secret="whsec_wrong")[0], 401)
        self.assertEqual(call_webhook(ev, ts=int(time.time()) - 3600)[0], 401)   # replayed old but validly-signed request
        self.assertEqual(call_webhook(ev, ts=int(time.time()) + 3600)[0], 401)
        body = b"not json"
        set_request(body, docuseal.sign(SECRET, body))
        self.assertEqual(inspect.unwrap(docuseal.webhook)()["message"], "malformed")
        self.assertEqual(frappe.db.count("AO Integration Event"), n0)   # nothing recorded for rejected requests
        # authenticated but unknown submission -> recorded and ignored, never crashes
        self.assertEqual(call_webhook(ev), (200, "accepted"))
        e = frappe.get_doc("AO Integration Event", {"event_key": "docuseal:form.completed:777:2026-10-19T10:00:00Z"})
        if e.status == "Received":
            docuseal.process_event(e.name); e.reload()
        self.assertEqual(e.status, "Ignored")

    def test_webhook_disabled_when_not_configured(self):
        s = frappe.get_doc("AO Settings"); s.docuseal_enabled = 0; s.save(ignore_permissions=True)
        try:
            self.assertEqual(call_webhook(event("form.completed", 1, "x"))[0], 503)
        finally:
            s.docuseal_enabled = 1; s.save(ignore_permissions=True)

    # ---- failure handling
    def test_docuseal_outage_is_contained_and_recoverable(self):
        cust, case = self._case_waiting_for_signature("ds2")
        fa = frappe.get_all("AO Form Approval", filters={"case": case}, pluck="name")[0]
        self.sim.fail = True
        try:
            with as_user(cust), self.assertRaises(frappe.ValidationError) as cm:
                portal_api.get_signing_url(case, fa)
            self.assertNotIn("boom", str(cm.exception))                        # no upstream detail leaked to customer
            row = frappe.get_doc("AO Form Approval", fa)
            self.assertEqual(row.submission_status, "Error")
            self.assertIn("HTTP 500", row.last_error or "")
            self.assertEqual(frappe.db.get_value("AO Application Case", case, "case_state"), "READY_FOR_CUSTOMER_APPROVAL")  # case untouched
        finally:
            self.sim.fail = False
        with as_user(self.worker):
            staff_api.sync_signing_request(fa)                                   # staff retry after recovery
        self.assertEqual(frappe.db.get_value("AO Form Approval", fa, "submission_status"), "Sent")

    def test_unreachable_docuseal_times_out_cleanly(self):
        s = frappe.get_doc("AO Settings"); old = s.docuseal_base_url
        s.docuseal_base_url = "http://127.0.0.1:9"; s.save(ignore_permissions=True)
        try:
            cust, case = self._case_waiting_for_signature("ds3")
            fa = frappe.get_all("AO Form Approval", filters={"case": case}, pluck="name")[0]
            with as_user(cust), self.assertRaises(frappe.ValidationError):
                portal_api.get_signing_url(case, fa)
            self.assertEqual(frappe.db.get_value("AO Form Approval", fa, "submission_status"), "Error")
        finally:
            s.docuseal_base_url = old; s.save(ignore_permissions=True)

    def test_failed_event_processing_is_retried(self):
        cust, case = self._case_waiting_for_signature("ds4")
        fa = frappe.get_all("AO Form Approval", filters={"case": case}, pluck="name")[0]
        ev = frappe.get_doc({"doctype": "AO Integration Event", "event_key": "docuseal:form.completed:5:retry", "source": "docuseal",
                             "event_type": "form.completed", "status": "Error", "attempts": 1,
                             "context": json.dumps({"event_type": "form.completed", "id": "502", "submission_id": "", "external_id": fa, "status": "completed"})}).insert(ignore_permissions=True)
        docuseal.retry_failed_events()
        ev.reload()
        self.assertEqual((ev.status, ev.attempts), ("Processed", 2))
        self.assertEqual(frappe.db.get_value("AO Form Approval", fa, "signature_status"), "Signed")

    def test_foreign_customer_cannot_get_signing_url(self):
        cust, case = self._case_waiting_for_signature("ds5")
        other, _ = make_customer("ds5b")
        fa = frappe.get_all("AO Form Approval", filters={"case": case}, pluck="name")[0]
        with as_user(other), self.assertRaises(frappe.DoesNotExistError):
            portal_api.get_signing_url(case, fa)

    def test_refuses_foreign_host_fetch(self):
        with self.assertRaises(frappe.ValidationError):
            docuseal._request("GET", "", absolute="http://169.254.169.254/latest/meta-data")
