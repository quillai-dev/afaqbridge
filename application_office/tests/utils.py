import contextlib
import json

import frappe
from frappe.utils import add_days, now_datetime, today

from application_office import customers, intake, uploads
from application_office.common import AO_ROLES

def _make_pdf(extra=b""):
    from io import BytesIO

    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(72, 72)
    buf = BytesIO()
    w.write(buf)
    return buf.getvalue()


PDF = _make_pdf()


@contextlib.contextmanager
def as_user(user):
    prev = frappe.session.user
    frappe.set_user(user)
    try:
        yield
    finally:
        frappe.set_user(prev)


def ensure_email_account():
    """Outgoing mail needs an Email Account. Messages are only queued in tests (nothing is sent)."""
    if frappe.db.exists("Email Account", {"default_outgoing": 1, "enable_outgoing": 1}):
        return
    frappe.get_doc({"doctype": "Email Account", "email_id": "office@example.invalid", "email_account_name": "AO Test Outgoing",
                    "enable_outgoing": 1, "default_outgoing": 1, "smtp_server": "localhost", "smtp_port": 25,
                    "use_tls": 0, "enable_incoming": 0, "password": "unused"}).insert(ignore_permissions=True)


def ensure_ao_settings():
    ensure_email_account()
    s = frappe.get_doc("AO Settings")
    s.docuseal_enabled = 0
    s.save(ignore_permissions=True)


def make_staff(tag, *roles):
    email = f"{tag}@staff.test"
    if frappe.db.exists("User", email):
        return email
    frappe.get_doc({"doctype": "User", "email": email, "first_name": tag, "user_type": "System User",
                    "send_welcome_email": 0, "roles": [{"role": r} for r in roles]}).insert(ignore_permissions=True)
    return email


def make_customer(tag, consents=True):
    email = f"{tag}@cust.test"
    res = customers.create_customer_with_user(
        email, f"Customer {tag}", "en",
        {"Terms of Service": 1, "Privacy Notice": 1, "Sensitive Data Processing": 1} if consents else {},
        invited_by=None if consents else "Administrator", send_welcome=False)
    return email, res["customer"]


def make_program(name="Test Program", published=True, closing_days=30, **kw):
    if frappe.db.exists("AO Program", name):
        return frappe.get_doc("AO Program", name)
    d = {"doctype": "AO Program", "program_name": name, "program_category": "Scholarship",
         "published": 1 if published else 0, "service_available": 1, "responsible_employee": "Administrator",
         "last_verified_on": today(), "time_zone": "Europe/Berlin", "customer_approval_required": 1,
         "closing_datetime": add_days(now_datetime(), closing_days),
         "document_requirements": [
             {"document_category": "Passport", "required": 1, "retention_category": "Identity Document"},
             {"document_category": "Diploma", "required": 1, "retention_category": "Educational Record"},
             {"document_category": "Extra", "required": 0, "retention_category": "Other"}],
         "intake_fields": [
             {"field_key": "full_name", "label": "Full name", "field_type": "Text", "required": 1},
             {"field_key": "passport_number", "label": "Passport number", "field_type": "Text", "required": 1, "sensitive": 1}]}
    d.update(kw)
    return frappe.get_doc(d).insert(ignore_permissions=True)


def start_case_for(customer_email, program):
    from application_office import portal_api
    with as_user(customer_email):
        return portal_api.start_case(program)["case"]


def fill_intake(customer_email, case):
    from application_office import portal_api
    with as_user(customer_email):
        portal_api.save_intake(case, json.dumps({"full_name": "Ada Lovelace", "passport_number": "X1234567"}), 1)


def upload_all(case, customer_email, categories=None):
    for rd in frappe.get_all("AO Required Document", filters={"case": case}, fields=["name", "document_category", "required"]):
        if rd.required and (categories is None or rd.document_category in categories):
            doc = frappe.get_doc("AO Required Document", rd.name)
            with as_user(customer_email):
                uploads.store_version(doc, "scan.pdf", PDF + b"\n%" + rd.name.encode())


def customer_submit(case, customer_email):
    from application_office import portal_api
    with as_user(customer_email):
        portal_api.submit_to_office(case)


def approve_docs(case, reviewer):
    from application_office import staff_api
    with as_user(reviewer):
        for rd in frappe.get_all("AO Required Document", filters={"case": case, "upload_status": "Uploaded"}, pluck="name"):
            staff_api.review_document(rd, "Approved", "ok")


def drive_to_ready_for_submission(program, cust_email, worker, reviewer):
    """Customer journey up to READY_FOR_SUBMISSION. Returns the case name."""
    from application_office import portal_api, staff_api
    case = start_case_for(cust_email, program)
    fill_intake(cust_email, case)
    upload_all(case, cust_email)
    customer_submit(case, cust_email)
    approve_docs(case, reviewer)
    with as_user(reviewer):
        staff_api.transition(case, "READY_FOR_CUSTOMER_APPROVAL")
    with as_user(cust_email):
        portal_api.approve_case(case, 1)
    return case
