"""Customer notifications: configurable templates, de-duplication, delivery tracking.

Delivery status caveat: Frappe's Email Queue 'Sent' means the SMTP server accepted the message;
it is not proof the customer's mailbox received it."""
from __future__ import annotations

import frappe
from frappe.utils import get_url, now_datetime

from application_office import audit
from application_office.common import customer_email, settings

EVENTS = ["registration_success", "application_received", "missing_documents", "correction_request",
          "review_complete", "approval_request", "deadline_reminder", "submission_recorded",
          "official_update", "invoice_outstanding", "case_closed"]

_DEFAULT_BODY = {
    "registration_success": ("Welcome to {{ office_name }}", "<p>Hello {{ customer_name }},</p><p>Your account is ready.</p>{% if set_password_url %}<p>Please set your password (this also confirms your e-mail address): <a href='{{ set_password_url }}'>{{ set_password_url }}</a></p>{% endif %}<p>Then sign in at <a href='{{ portal_url }}'>{{ portal_url }}</a>.</p><p>{{ disclaimer }}</p>"),
    "application_received": ("We received your application {{ case_reference }}", "<p>Hello {{ customer_name }},</p><p>We opened case <b>{{ case_reference }}</b> for {{ program_name }}. Please upload the requested documents in your portal.</p>"),
    "missing_documents": ("Documents needed for {{ case_reference }}", "<p>Hello {{ customer_name }},</p><p>We still need documents for case {{ case_reference }}.</p>{% if message %}<p>{{ message }}</p>{% endif %}<p><a href='{{ portal_url }}'>Open your portal</a></p>"),
    "correction_request": ("Action needed on {{ case_reference }}", "<p>Hello {{ customer_name }},</p><p>Corrections are needed for case {{ case_reference }}.</p>{% if message %}<p>{{ message }}</p>{% endif %}<p><a href='{{ portal_url }}'>Open your portal</a></p>"),
    "review_complete": ("Document review finished for {{ case_reference }}", "<p>Hello {{ customer_name }},</p><p>We finished reviewing a document for case {{ case_reference }}. Status: {{ status_label }}.</p>{% if message %}<p>{{ message }}</p>{% endif %}"),
    "approval_request": ("Please review and approve {{ case_reference }}", "<p>Hello {{ customer_name }},</p><p>Your application information is ready for your approval. Nothing is submitted until you approve and our staff submit it on the official website.</p><p><a href='{{ portal_url }}'>Review and approve</a></p>"),
    "deadline_reminder": ("Deadline reminder for {{ case_reference }}", "<p>Hello {{ customer_name }},</p><p>The deadline we have on record for {{ program_name }} is <b>{{ deadline }}</b>. Current status: {{ status_label }}.</p><p>Please confirm dates on the official website; deadlines can change.</p>"),
    "submission_recorded": ("Submission recorded for {{ case_reference }}", "<p>Hello {{ customer_name }},</p><p>Our staff recorded that your application was submitted on the official website. This does not mean it was accepted or selected.</p>"),
    "official_update": ("Update on {{ case_reference }}", "<p>Hello {{ customer_name }},</p><p>Status: {{ status_label }}.</p>{% if message %}<p>{{ message }}</p>{% endif %}"),
    "invoice_outstanding": ("Outstanding invoice {{ case_reference }}", "<p>Hello {{ customer_name }},</p><p>You have an outstanding invoice. {{ message }}</p>"),
    "case_closed": ("Case {{ case_reference }} closed", "<p>Hello {{ customer_name }},</p><p>Case {{ case_reference }} is now closed. Records are kept according to our retention policy.</p>"),
}



# Arabic defaults (same Jinja variables). Seeded as "<event>-ar"; existing administrator edits are never overwritten.
_DEFAULT_BODY_AR = {
    "registration_success": ("مرحبًا بك في {{ office_name }}", "<p>مرحبًا {{ customer_name }}،</p><p>حسابك جاهز.</p>{% if set_password_url %}<p>يُرجى تعيين كلمة المرور (وهذا يؤكد أيضًا عنوان بريدك الإلكتروني): <a href='{{ set_password_url }}'>{{ set_password_url }}</a></p>{% endif %}<p>ثم سجّل الدخول عبر <a href='{{ portal_url }}'>{{ portal_url }}</a>.</p><p>{{ disclaimer }}</p>"),
    "application_received": ("استلمنا طلبك {{ case_reference }}", "<p>مرحبًا {{ customer_name }}،</p><p>فتحنا الملف <b>{{ case_reference }}</b> لبرنامج {{ program_name }}. يُرجى رفع المستندات المطلوبة عبر بوابتك.</p>"),
    "missing_documents": ("مستندات مطلوبة للملف {{ case_reference }}", "<p>مرحبًا {{ customer_name }}،</p><p>ما زلنا بحاجة إلى مستندات للملف {{ case_reference }}.</p>{% if message %}<p>{{ message }}</p>{% endif %}<p><a href='{{ portal_url }}'>افتح بوابتك</a></p>"),
    "correction_request": ("مطلوب إجراء بخصوص {{ case_reference }}", "<p>مرحبًا {{ customer_name }}،</p><p>هناك تصحيحات مطلوبة للملف {{ case_reference }}.</p>{% if message %}<p>{{ message }}</p>{% endif %}<p><a href='{{ portal_url }}'>افتح بوابتك</a></p>"),
    "review_complete": ("اكتملت مراجعة المستند للملف {{ case_reference }}", "<p>مرحبًا {{ customer_name }}،</p><p>أنهينا مراجعة مستند للملف {{ case_reference }}. الحالة: {{ status_label }}.</p>{% if message %}<p>{{ message }}</p>{% endif %}"),
    "approval_request": ("يُرجى مراجعة {{ case_reference }} والموافقة عليه", "<p>مرحبًا {{ customer_name }}،</p><p>بيانات طلبك جاهزة لموافقتك. لن يُقدَّم أي شيء قبل موافقتك وقبل أن يقدّمه فريقنا على الموقع الرسمي.</p><p><a href='{{ portal_url }}'>راجع ووافق</a></p>"),
    "deadline_reminder": ("تذكير بالموعد النهائي للملف {{ case_reference }}", "<p>مرحبًا {{ customer_name }}،</p><p>الموعد النهائي المسجّل لدينا لبرنامج {{ program_name }} هو <b>{{ deadline }}</b>. الحالة الحالية: {{ status_label }}.</p><p>يُرجى التأكد من المواعيد على الموقع الرسمي، فقد تتغير المواعيد النهائية.</p>"),
    "submission_recorded": ("تم تسجيل التقديم للملف {{ case_reference }}", "<p>مرحبًا {{ customer_name }}،</p><p>سجّل فريقنا أن طلبك قد قُدّم على الموقع الرسمي. هذا لا يعني أنه قُبل أو تم اختياره.</p>"),
    "official_update": ("تحديث بخصوص {{ case_reference }}", "<p>مرحبًا {{ customer_name }}،</p><p>الحالة: {{ status_label }}.</p>{% if message %}<p>{{ message }}</p>{% endif %}"),
    "invoice_outstanding": ("فاتورة مستحقة {{ case_reference }}", "<p>مرحبًا {{ customer_name }}،</p><p>لديك فاتورة مستحقة. {{ message }}</p>"),
    "case_closed": ("تم إغلاق الملف {{ case_reference }}", "<p>مرحبًا {{ customer_name }}،</p><p>تم إغلاق الملف {{ case_reference }}. تُحفظ السجلات وفق سياسة الاحتفاظ لدينا.</p>"),
}

_OLD_REG = "<p>Hello {{ customer_name }},</p><p>Your account is ready. Sign in at <a href='{{ portal_url }}'>{{ portal_url }}</a>.</p><p>{{ disclaimer }}</p>"


def seed_templates():
    for lang, bodies in (("en", _DEFAULT_BODY), ("ar", _DEFAULT_BODY_AR)):
        _seed_language(lang, bodies)


def _seed_language(lang, bodies):
    for key, (subject, body) in bodies.items():
        name = f"{key}-{lang}"
        if frappe.db.exists("AO Notification Template", name):
            # upgrade an untouched previous default body (never overwrite administrator edits)
            if lang == "en" and key == "registration_success" and frappe.db.get_value("AO Notification Template", name, "body") == _OLD_REG:
                frappe.db.set_value("AO Notification Template", name, "body", body)
        else:
            frappe.get_doc({"doctype": "AO Notification Template", "event_key": key, "language": lang,
                            "enabled": 1, "subject": subject, "body": body}).insert(ignore_permissions=True)


def _template(event_key: str, language: str | None):
    for lang in filter(None, [language, (language or "")[:2], "en"]):
        name = f"{event_key}-{lang}"
        if frappe.db.exists("AO Notification Template", name):
            return frappe.get_doc("AO Notification Template", name)
    return None


def _log(dedupe_key: str, **values):
    """Insert the log row first: the UNIQUE dedupe_key is the idempotency guard."""
    try:
        doc = frappe.get_doc({"doctype": "AO Notification Log", "dedupe_key": dedupe_key, **values})
        doc.insert(ignore_permissions=True)
        return doc
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        return None


def send(event_key: str, customer: str, dedupe_key: str, context: dict | None = None, case: str | None = None):
    """Queue one email. Returns the log doc, or None when a duplicate / not deliverable."""
    if frappe.db.exists("AO Notification Log", {"dedupe_key": dedupe_key}):
        return None
    cust = frappe.db.get_value("Customer", customer, ["customer_name", "language", "disabled"], as_dict=True)
    recipient = customer_email(customer)
    if not cust or cust.disabled or not recipient:
        _log(dedupe_key, event_key=event_key, case=case, customer=customer, status="Skipped",
             error="No active recipient")
        return None
    tpl = _template(event_key, cust.language)
    if not tpl or not tpl.enabled:
        _log(dedupe_key, event_key=event_key, case=case, customer=customer, recipient=recipient,
             status="Skipped", error="Template missing or disabled")
        return None
    s = settings()
    from application_office.install import DEFAULT_DISCLAIMER
    from application_office.localization import translate_if_default, language
    with language(cust.language):  # the disclaimer is rendered in the RECIPIENT's language
        disclaimer = translate_if_default(s.disclaimer_text, DEFAULT_DISCLAIMER)
    ctx = {"customer_name": cust.customer_name, "office_name": s.office_name,
           "disclaimer": disclaimer, "portal_url": get_url("/office-portal"),
           "case_reference": case or "", **(context or {})}
    log = _log(dedupe_key, event_key=event_key, case=case, customer=customer, recipient=recipient, status="Queued")
    if not log:
        return None
    try:
        subject = frappe.render_template(tpl.subject, ctx)
        body = frappe.render_template(tpl.body, ctx)
        frappe.sendmail(recipients=[recipient], subject=subject, message=body,
                        reference_doctype="AO Notification Log", reference_name=log.name, delayed=True)
        queue = frappe.db.get_value("Email Queue", {"reference_doctype": "AO Notification Log",
                                                    "reference_name": log.name}, "name")
        log.db_set("email_queue", queue, update_modified=False)
    except Exception as e:  # never let a mail problem roll back a business transaction
        log.db_set({"status": "Error", "error": f"{type(e).__name__}: {str(e)[:200]}"}, update_modified=False)
        frappe.log_error(title="AO notification failed", message=f"{event_key} {dedupe_key}: {type(e).__name__}")
    return log


def notify_case(event_key: str, case, dedupe_key: str, message: str | None = None, extra: dict | None = None):
    from application_office.workflow import status_label
    from application_office.localization import language
    from application_office.scheduler import format_deadline
    program = frappe.db.get_value("AO Program", case.program, ["program_name", "time_zone"], as_dict=True)
    with language(frappe.db.get_value("Customer", case.customer, "language")):  # recipient's language
        label = status_label(case.case_state)
    ctx = {"program_name": program.program_name,
           "status_label": label,
           "deadline": format_deadline(case.applicable_deadline, program.time_zone) if case.applicable_deadline else "",
           "message": message or "", **(extra or {})}
    return send(event_key, case.customer, dedupe_key, ctx, case=case.name)


def refresh_delivery_status():
    """Copy Email Queue outcomes onto our log rows (hourly job)."""
    for row in frappe.get_all("AO Notification Log", filters={"status": "Queued", "email_queue": ["is", "set"]},
                              fields=["name", "email_queue"], limit=200):
        st = frappe.db.get_value("Email Queue", row.email_queue, ["status", "error"], as_dict=True)
        if not st:
            continue
        if st.status == "Sent":
            frappe.db.set_value("AO Notification Log", row.name, {"status": "Sent", "sent_at": now_datetime()})
        elif st.status in ("Error", "Expired"):
            frappe.db.set_value("AO Notification Log", row.name,
                                {"status": "Error", "error": (st.error or st.status)[:200]})
