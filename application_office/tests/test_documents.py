import frappe
from frappe.tests import IntegrationTestCase

from application_office import staff_api, uploads
from application_office.tests.utils import *  # noqa: F401,F403
from application_office.tests.utils import PDF


class TestDocuments(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ensure_ao_settings()
        cls.worker = make_staff("dw", "AO Case Worker")
        cls.reviewer = make_staff("drev", "AO Reviewer")
        cls.program = make_program().name
        cls.cust, _ = make_customer("docs")
        cls.case = start_case_for(cls.cust, cls.program)
        cls.rd = frappe.get_all("AO Required Document", filters={"case": cls.case, "document_category": "Passport"}, pluck="name")[0]

    def doc(self):
        return frappe.get_doc("AO Required Document", self.rd)

    def test_validation_rejections(self):
        v = uploads.validate
        for name, content in (("a.pdf", b""), ("a.exe", PDF), ("a.pdf", b"MZ\x90\x00 not a pdf"),
                              ("a.png", PDF), ("a.pdf", PDF + b"/JavaScript (alert(1))"),
                              ("noext", PDF), ("a.pdf", b"%PDF-1.4 garbage")):
            with self.assertRaises(uploads.UploadRejected, msg=name):
                v(name, content)
        with self.assertRaises(uploads.UploadRejected):  # size limit
            frappe.db.set_single_value("AO Settings", "max_upload_mb", 1)
            frappe.clear_cache()
            v("big.pdf", PDF + b"0" * (1024 * 1024 + 1))
        frappe.db.set_single_value("AO Settings", "max_upload_mb", 10)
        frappe.clear_cache()
        png = b"\x89PNG\r\n\x1a\n" + b"\0" * 20
        self.assertEqual(v("x.png", png), ("png", "image/png"))
        self.assertEqual(v("x.PDF", PDF)[0], "pdf")

    def test_upload_is_private_versioned_and_renamed(self):
        d = self.doc()
        f1 = uploads.store_version(d, "../../etc/passwd.pdf", PDF + b"1")
        d = self.doc()
        f2 = uploads.store_version(d, "my passport (2).pdf", PDF + b"2")
        d = self.doc()
        last = [v.version for v in d.versions][-2:]
        self.assertEqual(last[1], last[0] + 1)
        self.assertEqual(d.current_version, last[1])
        for f in (f1, f2):
            self.assertEqual(f.is_private, 1)
            self.assertTrue(f.file_url.startswith("/private/files/"))
            self.assertNotIn("(2)", f.file_name); self.assertNotIn("etc", f.file_name)  # user-supplied names are never used on disk
            self.assertNotIn("..", f.file_name)
        self.assertNotEqual(d.versions[0].sha256, d.versions[1].sha256)
        self.assertEqual(d.upload_status, "Uploaded")

    def test_versions_and_status_are_immutable_for_normal_saves(self):
        d = self.doc()
        uploads.store_version(d, "a.pdf", PDF + b"3")
        d = self.doc()
        d.review_status = "Approved"
        with self.assertRaises(frappe.PermissionError):
            d.save(ignore_permissions=True)
        d = self.doc()
        d.versions[0].sha256 = "tampered"
        with self.assertRaises(frappe.PermissionError):
            d.save(ignore_permissions=True)

    def test_review_correction_and_reupload(self):
        d = self.doc()
        uploads.store_version(d, "a.pdf", PDF + b"4")
        v = self.doc().current_version
        with as_user(self.reviewer):
            with self.assertRaises(frappe.ValidationError):  # corrections must be described
                staff_api.review_document(self.rd, "Correction Required", "blurry")
            r = staff_api.review_document(self.rd, "Correction Required", "blurry", "Rescan in colour", "Please rescan in colour")
        d = self.doc()
        self.assertEqual(r["version_reviewed"], v)
        self.assertEqual(d.review_status, "Correction Required")
        self.assertEqual(d.customer_feedback, "Please rescan in colour")
        self.assertEqual(d.reviewer, self.reviewer)
        self.assertTrue(d.review_timestamp)
        uploads.store_version(d, "a.pdf", PDF + b"5")
        d = self.doc()
        self.assertEqual((d.review_status, d.current_version, d.customer_feedback), ("Pending", v + 1, None))
        with as_user(self.reviewer):
            staff_api.review_document(self.rd, "Approved", "good")
        self.assertEqual(self.doc().review_status, "Approved")
        review = frappe.get_all("AO Document Review", filters={"required_document": self.rd}, pluck="name")[0]
        rv = frappe.get_doc("AO Document Review", review)
        rv.findings = "edited"
        with self.assertRaises(frappe.PermissionError):
            rv.save(ignore_permissions=True)
        self.assertTrue(frappe.db.exists("AO Audit Event", {"action": "document.reviewed", "ref_doctype": "AO Document Review"}))

    def test_case_worker_cannot_review(self):
        d = self.doc(); uploads.store_version(d, "a.pdf", PDF + b"6")
        with as_user(self.worker), self.assertRaises(frappe.PermissionError):
            staff_api.review_document(self.rd, "Approved")

    def test_cannot_review_nothing(self):
        other = frappe.get_all("AO Required Document", filters={"case": self.case, "document_category": "Diploma"}, pluck="name")[0]
        with as_user(self.reviewer), self.assertRaises(frappe.ValidationError):
            staff_api.review_document(other, "Approved")
