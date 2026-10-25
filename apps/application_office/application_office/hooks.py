app_name = "application_office"
app_title = "AfaqBridge"
app_publisher = "AfaqBridge"
app_description = "AfaqBridge: international applications and administrative services platform (Arabic-first, English optional)"
app_logo_url = "/assets/application_office/images/afaqbridge-icon.svg"

# Branding + Arabic-first behaviour (see localization.py). The CSS only fixes direction-sensitive details Frappe
# does not handle itself; the JS adds the AR/EN switch to the desk navbar.
app_include_css = ["/assets/application_office/css/afaqbridge_desk.css"]
app_include_js = ["/assets/application_office/js/language_switcher.js"]
website_context = {
    "favicon": "/assets/application_office/images/favicon.svg",
    "splash_image": "/assets/application_office/images/afaqbridge-icon.svg",
}
before_request = ["application_office.localization.before_request"]
after_request = ["application_office.localization.after_request"]
doc_events = {"User": {"before_insert": "application_office.localization.user_before_insert"}}
app_email = "admin@example.invalid"
app_license = "mit"
required_apps = ["erpnext"]

after_install = "application_office.install.after_install"
after_migrate = "application_office.install.after_migrate"

doctype_js = {"AO Application Case": "public/js/application_case.js"}

permission_query_conditions = {
    "AO Application Case": "application_office.permissions.case_query",
    "AO Required Document": "application_office.permissions.required_document_query",
    "AO Document Review": "application_office.permissions.document_review_query",
    "AO Form Approval": "application_office.permissions.form_approval_query",
    "AO Official Submission": "application_office.permissions.official_submission_query",
    "AO Referral": "application_office.permissions.referral_query",
    "AO Case Message": "application_office.permissions.case_message_query",
}

has_permission = {
    "AO Application Case": "application_office.permissions.case_has_permission",
    "AO Required Document": "application_office.permissions.child_has_permission",
    "AO Document Review": "application_office.permissions.child_has_permission",
    "AO Form Approval": "application_office.permissions.child_has_permission",
    "AO Official Submission": "application_office.permissions.child_has_permission",
    "AO Referral": "application_office.permissions.child_has_permission",
    "AO Case Message": "application_office.permissions.child_has_permission",
    "AO Program": "application_office.permissions.deny_portal",
    "AO Audit Event": "application_office.permissions.deny_portal",
    "AO Consent Record": "application_office.permissions.deny_portal",
    "AO Data Request": "application_office.permissions.deny_portal",
    "AO Settings": "application_office.permissions.deny_portal",
}

scheduler_events = {
    "hourly": ["application_office.scheduler.hourly"],
    "daily": ["application_office.scheduler.daily"],
}

website_route_rules = [{"from_route": "/office-portal/<path:app_path>", "to_route": "office-portal"}]

# Paths that must never be indexed or cached
website_redirects = []
