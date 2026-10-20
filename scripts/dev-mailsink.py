#!/usr/bin/env python3
"""Dev SMTP sink: accepts mail on 127.0.0.1:1025 and stores it as /tmp/mailsink/<n>.eml. Nothing leaves the machine."""
import asyncio, os, itertools
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword
os.makedirs("/tmp/mailsink", exist_ok=True)
n = itertools.count(len(os.listdir("/tmp/mailsink")) + 1)
class H:
    async def handle_DATA(self, server, session, envelope):
        open(f"/tmp/mailsink/{next(n)}.eml", "wb").write(b"To: " + ",".join(envelope.rcpt_tos).encode() + b"\n" + envelope.content)
        return "250 OK"
async def main():
    def auth(server, session, envelope, mechanism, auth_data):
        return AuthResult(success=True)   # dev sink: accept any credentials
    c = Controller(H(), hostname="127.0.0.1", port=1025, authenticator=auth, auth_required=False, auth_require_tls=False)
    c.start()
    await asyncio.Event().wait()

asyncio.run(main())
