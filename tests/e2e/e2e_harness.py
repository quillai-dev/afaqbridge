"""Server-side fixtures/inspection for the browser E2E (run through scripts/frappe_run.py)."""
import json, os, re, secrets, time
import frappe

STATE = "/tmp/e2e/state.json"
SIM_PORT = 9100


def setup():
    from frappe.utils import add_days, now_datetime, today
    from frappe.utils.password import update_password
    from frappe.twofactor import get_otpsecret_for_
    os.makedirs("/tmp/e2e", exist_ok=True)
    tag = secrets.token_hex(3)
    st = {"tag": tag, "staff": {}, "ds_token": "ds-" + secrets.token_hex(8), "ds_secret": "whsec_" + secrets.token_hex(16)}
    frappe.set_user("Administrator")
    # settings (DocuSeal -> SIMULATOR on localhost)
    s = frappe.get_doc("AO Settings")
    s.office_name = "Example Office"; s.terms_url = "https://example.invalid/terms"; s.privacy_url = "https://example.invalid/privacy"
    s.docuseal_enabled = 1; s.docuseal_base_url = f"http://127.0.0.1:{SIM_PORT}"
    s.docuseal_api_token = st["ds_token"]; s.docuseal_webhook_secret = st["ds_secret"]
    s.save(ignore_permissions=True)
    # program
    name = f"E2E Program {tag}"
    frappe.get_doc({"doctype": "AO Program", "program_name": name, "program_category": "Scholarship", "published": 1, "service_available": 1,
                    "responsible_employee": "Administrator", "last_verified_on": today(), "time_zone": "Europe/Berlin",
                    "closing_datetime": add_days(now_datetime(), 30), "customer_approval_required": 1,
                    "eligibility_information": "<p>Open to adults.</p>",
                    "document_requirements": [{"document_category": "Passport", "required": 1, "retention_category": "Identity Document"},
                                              {"document_category": "Diploma", "required": 1, "retention_category": "Educational Record"}],
                    "intake_fields": [{"field_key": "full_name", "label": "Full name", "field_type": "Text", "required": 1},
                                      {"field_key": "passport_number", "label": "Passport number", "field_type": "Text", "required": 1, "sensitive": 1}],
                    "form_templates": [{"form_name": "Application form", "docuseal_template_id": "7", "signature_required": 1}]}
                   ).insert(ignore_permissions=True)
    st["program"] = name
    for key, roles in (("worker", ["AO Case Worker"]), ("reviewer", ["AO Reviewer"]), ("finance", ["AO Finance", "Accounts User"])):
        email = f"e2e-{key}-{tag}@staff.test"; pwd = "E2e!Pass-" + secrets.token_hex(5)
        frappe.get_doc({"doctype": "User", "email": email, "first_name": key.title(), "user_type": "System User", "send_welcome_email": 0,
                        "roles": [{"role": r} for r in roles]}).insert(ignore_permissions=True)
        update_password(email, pwd)
        secret = get_otpsecret_for_(email)
        frappe.defaults.set_user_default("_otplogin", 1, user=email) if False else frappe.db.set_default(email + "_otplogin", 1)
        st["staff"][key] = {"email": email, "password": pwd, "otp_secret": secret}
    st["customer"] = {"email": f"e2e-{tag}@customer.test", "name": f"Eva Example {tag}", "password": "Cust!Pass-" + secrets.token_hex(5)}
    frappe.db.commit()
    json.dump(st, open(STATE, "w"), indent=1)
    print("setup ok", tag)


def _msg_text(raw):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw or ""))


def set_password_link():
    st = json.load(open(STATE)); email = st["customer"]["email"]
    row = frappe.db.sql("""select q.message from `tabEmail Queue` q join `tabEmail Queue Recipient` r on r.parent=q.name
                           where r.recipient=%s order by q.creation desc limit 1""", email)
    import email as emaillib
    msg = emaillib.message_from_string(row[0][0]) if row else None
    text = ""
    if msg:
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                text += part.get_payload(decode=True).decode("utf-8", "replace")
    m = re.search(r"href=['\"]([^'\"]*update-password[^'\"]*)['\"]", text)
    print("LINK", m.group(1) if m else "")


def flush():
    frappe.set_user("Administrator")
    from frappe.email.queue import flush as f
    for _ in range(14):
        frappe.db.rollback(); f(); frappe.db.commit()
        if not frappe.db.count("Email Queue", {"status": "Not Sent"}):
            break
        time.sleep(1)
    print("queue", frappe.db.sql("select status,count(*) from `tabEmail Queue` group by status"))


def report():
    st = json.load(open(STATE)); email = st["customer"]["email"]
    cust = frappe.db.get_value("Portal User", {"user": email}, "parent")
    out = {"customer": cust, "cases": [], "notifications": [], "invoices": [], "audit": {}}
    for c in frappe.get_all("AO Application Case", filters={"customer": cust}, fields=["name", "case_state", "final_customer_approval_status",
                            "official_confirmation_reference", "retention_until", "closure_date"]):
        c["state_log"] = [f"{l.from_state}>{l.to_state}" for l in frappe.get_doc("AO Application Case", c.name).state_log]
        c["docs"] = frappe.get_all("AO Required Document", filters={"case": c.name}, fields=["document_category", "review_status", "current_version"])
        c["forms"] = frappe.get_all("AO Form Approval", filters={"case": c.name}, fields=["signature_status", "submission_status", "signed_document_file"])
        c["submission"] = frappe.get_all("AO Official Submission", filters={"case": c.name}, fields=["submitted_by", "official_confirmation_number", "official_portal"])
        out["cases"].append(c)
        out["audit"][c.name] = sorted({a for a in frappe.get_all("AO Audit Event", filters={"case": c.name}, pluck="action")})
        out["invoices"] += frappe.get_all("Sales Invoice", filters={"ao_application_case": c.name}, fields=["name", "docstatus", "status", "grand_total", "currency"])
    out["notifications"] = frappe.get_all("AO Notification Log", filters={"customer": cust}, fields=["event_key", "status", "creation"], order_by="creation asc")
    for n in out["notifications"]: n["creation"] = str(n["creation"])
    print("REPORT", json.dumps(out, default=str))
