"""Dev-only bootstrap helpers executed through `bench execute` (see dev-site.sh)."""
import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete


def company():
    if frappe.is_setup_complete():
        return
    setup_complete({"language": "English", "country": "Netherlands", "timezone": "Europe/Amsterdam", "currency": "EUR",
                    "full_name": "Dev Admin", "email": "dev-admin@example.invalid", "password": "admin-dev-only",
                    "company_name": "Example Office BV", "company_abbr": "EO", "chart_of_accounts": "Standard",
                    "fy_start_date": "2026-01-01", "fy_end_date": "2026-12-31", "enable_telemetry": 0})
    frappe.db.commit()


def finish():
    """Items that need the Company to exist (AO-SERVICE item) and a dev outgoing mail account."""
    from application_office.install import seed
    seed()
    if not frappe.db.exists("Email Account", {"default_outgoing": 1}):
        frappe.flags.in_patch = True  # skip SMTP connectivity validation: dev account only queues mail
        frappe.get_doc({"doctype": "Email Account", "email_id": "office@example.invalid", "email_account_name": "Dev Outgoing",
                        "enable_outgoing": 1, "default_outgoing": 1, "smtp_server": "127.0.0.1", "smtp_port": 1025,
                        "use_tls": 0, "enable_incoming": 0, "no_smtp_authentication": 1}).insert(ignore_permissions=True)
        frappe.flags.in_patch = False
    frappe.db.commit()
