import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class AODataRequest(Document):
    def before_insert(self):
        self.received_at = now_datetime()
