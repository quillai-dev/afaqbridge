#!/usr/bin/env python3
"""SIMULATED DocuSeal for browser E2E. NOT the real product.
Implements only what application_office uses, with shapes verified from docuseal 3.3.2 source:
  POST /api/submissions (X-Auth-Token) -> [{id, submission_id, slug, embed_src, external_id}]
  GET  /api/submissions/:id/documents  -> {documents:[{name,url}]}
  GET  /s/:slug                        -> a page with a Sign button (stands in for DocuSeal's signing UI)
  POST /s/:slug/complete               -> sends an HMAC-signed `form.completed` webhook to Frappe, then 303 -> portal
Env: DS_PORT, DS_TOKEN, DS_SECRET, FRAPPE_URL (e.g. http://office.localhost:8000)"""
import hashlib, hmac, io, json, os, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("DS_PORT", 9100)); TOKEN = os.environ["DS_TOKEN"]; SECRET = os.environ["DS_SECRET"]
FRAPPE = os.environ.get("FRAPPE_URL", "http://office.localhost:8000")
subs, counter = {}, [4000]
LOG = open(os.environ.get("DS_LOG", "/tmp/docuseal_sim.log"), "a")

def pdf():
    from pypdf import PdfWriter
    w = PdfWriter(); w.add_blank_page(72, 72); b = io.BytesIO(); w.write(b); return b.getvalue()

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); raw = self.rfile.read(n)
        LOG.write(f"POST {self.path}\n"); LOG.flush()
        if self.path == "/api/submissions":
            if self.headers.get("X-Auth-Token") != TOKEN: return self.send(401, {"error": "Not authorized"})
            body = json.loads(raw); s = body["submitters"][0]; counter[0] += 1
            slug = f"slug{counter[0]}"; subs[slug] = {"sid": counter[0], "ext": s.get("external_id"), "email": s["email"]}
            return self.send(200, [{"id": counter[0] + 100, "submission_id": counter[0], "slug": slug, "email": s["email"],
                                    "external_id": s.get("external_id"), "status": "awaiting", "embed_src": f"http://office.localhost:{PORT}/s/{slug}"}])
        if self.path.startswith("/s/") and self.path.endswith("/complete"):
            slug = self.path.split("/")[2]; s = subs.get(slug)
            if not s: return self.send(404, {})
            payload = json.dumps({"event_type": "form.completed", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  "data": {"id": s["sid"] + 100, "submission_id": s["sid"], "external_id": s["ext"], "status": "completed",
                                           "email": s["email"], "submission": {"id": s["sid"]}}}).encode()
            ts = int(time.time()); sig = f"{ts}." + hmac.new(SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
            host = FRAPPE.split("//", 1)[1]   # e.g. office.localhost:8000 (not resolvable by Python; connect to loopback, keep the Host header)
            req = urllib.request.Request("http://127.0.0.1:" + host.split(":")[-1] + "/api/method/application_office.integrations.docuseal.webhook", data=payload,
                                         headers={"Content-Type": "application/json", "X-Docuseal-Signature": sig, "Host": host}, method="POST")
            try: code = urllib.request.urlopen(req, timeout=20).status
            except Exception as e: code = f"ERR {e}"
            LOG.write(f"webhook -> {code}\n"); LOG.flush()
            return self.send(303, b"", extra={"Location": f"{FRAPPE}/office-portal"})
        self.send(404, {})
    def do_GET(self):
        LOG.write(f"GET {self.path}\n"); LOG.flush()
        if self.path.startswith("/s/"):
            slug = self.path.split("/")[2]
            html = (f"<html><body><h1>SIMULATED DocuSeal signing page</h1><p>Not the real product.</p>"
                    f"<form method=post action='/s/{slug}/complete'><button id=sign type=submit>Sign</button></form></body></html>")
            return self.send(200, html.encode(), "text/html")
        if self.path.endswith("/documents") and self.path.startswith("/api/submissions/"):
            if self.headers.get("X-Auth-Token") != TOKEN: return self.send(401, {"error": "Not authorized"})
            return self.send(200, {"documents": [{"name": "signed", "url": f"http://127.0.0.1:{PORT}/files/signed.pdf"}]})
        if self.path.startswith("/files/"): return self.send(200, pdf(), "application/pdf")
        self.send(404, {})

HTTPServer(("127.0.0.1", PORT), H).serve_forever()
