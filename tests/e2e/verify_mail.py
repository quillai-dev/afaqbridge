#!/usr/bin/env python3
"""After an E2E run: list the notification log statuses and the mails the SMTP sink actually received for the E2E customer.
Exit 1 if any notification is not 'Sent' or the sink got fewer mails than notifications."""
import email, glob, json, re, sys
r = json.load(open("/home/claude/application-office/tests/e2e/artifacts/server-report.json"))
st = json.load(open("/tmp/e2e/state.json")); addr = st["customer"]["email"]
subs = []
for f in sorted(glob.glob("/tmp/mailsink/*.eml"), key=lambda x: int(re.search(r"(\d+)\.eml", x).group(1))):
    raw = open(f, errors="replace").read(); head, body = raw.split("\n", 1)
    if addr in head: subs.append(str(email.message_from_string(body)["Subject"]))
notes = [(n["event_key"], n["status"]) for n in r["notifications"]]
print("notification log:", notes); print(f"sink received {len(subs)} mails for {addr}:"); [print("  -", s) for s in subs]
bad = [n for n in notes if n[1] != "Sent"]
sys.exit(1 if bad or len(subs) < len(notes) else 0)
