import json

import frappe

from application_office.portal_strings import portal_messages

no_cache = 1


def get_context(context):
    """Hand the portal the gettext catalogue for the CURRENT request language (Frappe's own translation machinery),
    plus the language code. The JS never contains Arabic text itself."""
    context.no_cache = 1
    context.ao_lang = frappe.local.lang
    # '</' is escaped so the JSON can never close the <script> element
    context.ao_i18n_json = json.dumps(portal_messages(), ensure_ascii=False).replace("<", "\\u003c")
