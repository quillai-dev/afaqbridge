"""Scheduled jobs: deadline reminders (program time zone), invoice reminders, delivery status, retention."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import add_days, getdate, today

from application_office.common import settings, split_csv

OPEN_STATES = ("NEW", "WAITING_FOR_DOCUMENTS", "UNDER_REVIEW", "CORRECTION_REQUIRED",
               "READY_FOR_CUSTOMER_APPROVAL", "READY_FOR_SUBMISSION")


def _zone(tz: str | None):
    try:
        return ZoneInfo(tz or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def deadline_utc(deadline, tz: str | None) -> datetime:
    """Frappe Datetimes are naive; the case deadline is expressed in the program's time zone."""
    dt = frappe.utils.get_datetime(deadline)
    return dt.replace(tzinfo=_zone(tz)).astimezone(timezone.utc)


def format_deadline(deadline, tz: str | None) -> str:
    dt = frappe.utils.get_datetime(deadline).replace(tzinfo=_zone(tz))
    return dt.strftime("%Y-%m-%d %H:%M %Z")


def send_deadline_reminders(now: datetime | None = None) -> list[str]:
    """Send at most one reminder per (case, threshold): the tightest threshold already crossed."""
    thresholds = sorted({int(x) for x in split_csv(settings().reminder_days) if x.isdigit()})
    if not thresholds:
        return []
    now = now or datetime.now(timezone.utc)
    sent = []
    cases = frappe.get_all("AO Application Case", filters={
        "case_state": ["in", OPEN_STATES], "applicable_deadline": ["is", "set"], "deletion_status": ["!=", "Deleted"]},
        fields=["name", "applicable_deadline", "program"])
    for c in cases:
        tz = frappe.db.get_value("AO Program", c.program, "time_zone")
        remaining = deadline_utc(c.applicable_deadline, tz) - now
        if remaining.total_seconds() <= 0:
            continue
        days_left = remaining.total_seconds() / 86400
        crossed = [t for t in thresholds if days_left <= t]
        if not crossed:
            continue
        t = min(crossed)
        case = frappe.get_doc("AO Application Case", c.name)
        from application_office.notifications import notify_case
        if notify_case("deadline_reminder", case, dedupe_key=f"{c.name}:deadline:{t}:{c.applicable_deadline}"):
            sent.append(f"{c.name}:{t}")
    return sent


def send_invoice_reminders():
    grace = int(settings().invoice_reminder_days or 7)
    cutoff = add_days(today(), -grace)
    rows = frappe.get_all("Sales Invoice", filters={"docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", cutoff],
                                                    "ao_application_case": ["is", "set"]},
                          fields=["name", "customer", "ao_application_case", "outstanding_amount", "currency"])
    from application_office.notifications import send
    for r in rows:
        send("invoice_outstanding", r.customer, f"inv:{r.name}:overdue", case=r.ao_application_case,
             context={"message": f"Invoice {r.name}: {r.outstanding_amount:.2f} {r.currency} outstanding."})


def hourly():
    from application_office.notifications import refresh_delivery_status
    send_deadline_reminders()
    refresh_delivery_status()
    from application_office.integrations.docuseal import retry_failed_events
    retry_failed_events()


def daily():
    from application_office.retention import flag_eligible_cases
    send_invoice_reminders()
    flag_eligible_cases()
