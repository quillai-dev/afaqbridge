"""Regression tests for the public nginx edge (deploy/edge). They run the REAL edge-run.sh with a real nginx binary
against mock upstreams (no Docker needed). Needs root (binds 80/443 and writes /etc/nginx, /etc/letsencrypt).
  NGINX_BIN=/opt/nginx128/sbin/nginx python3 -m unittest tests.edge.test_edge_nginx -v
Skipped automatically when NGINX_BIN is not set or the process is not root."""
import http.client, json, os, shutil, signal, socket, ssl, subprocess, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NGINX = os.environ.get("NGINX_BIN")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EDGE = os.path.join(ROOT, "deploy/edge")
SITE, SIGN = "afaqbridge.localhost", "sign.afaqbridge.localhost"
FE_PORT, DS_PORT = 18080, 13001


class Echo(BaseHTTPRequestHandler):
    tag = "?"
    def log_message(self, *a): pass
    def _reply(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n: self.rfile.read(n)
        if self.path.startswith("/socket.io") and self.headers.get("Upgrade", "").lower() == "websocket":
            self.send_response(101); self.send_header("Upgrade", "websocket"); self.send_header("Connection", "Upgrade")
            self.send_header("X-Seen-Connection", self.headers.get("Connection", "")); self.end_headers(); return
        body = json.dumps({"who": self.tag, "path": self.path, "headers": dict(self.headers)}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    do_GET = do_POST = _reply


def serve(port, tag):
    h = type("H", (Echo,), {"tag": tag})
    s = ThreadingHTTPServer(("127.0.0.1", port), h); threading.Thread(target=s.serve_forever, daemon=True).start(); return s


def req(host, path="/", method="GET", headers=None, body=None, port=80, tls=False):
    c = (http.client.HTTPSConnection("127.0.0.1", port, context=ssl._create_unverified_context(), timeout=10) if tls
         else http.client.HTTPConnection("127.0.0.1", port, timeout=10))
    h = {"Host": host}; h.update(headers or {})
    c.request(method, path, body=body, headers=h); r = c.getresponse(); data = r.read(); c.close()
    return r, data


_servers = []


def setUpModule():
    if NGINX and os.geteuid() == 0:
        _servers.extend([serve(FE_PORT, "frontend"), serve(DS_PORT, "docuseal")])


def tearDownModule():
    for s in _servers: s.shutdown()


@unittest.skipUnless(NGINX and os.geteuid() == 0, "set NGINX_BIN and run as root")
class EdgeTests(unittest.TestCase):
    proc = None

    @classmethod
    def start(cls, mode):
        cls.stop()
        for d in ("/etc/nginx/conf.d", "/etc/nginx/afaqbridge"): shutil.rmtree(d, ignore_errors=True)
        os.makedirs("/etc/nginx/conf.d", exist_ok=True)
        conf = os.path.join(os.path.dirname(NGINX), "..", "conf", "nginx.conf")
        open(conf, "w").write("worker_processes 1; pid /tmp/edge-test.pid; error_log /tmp/edge-error.log info;\n"
                              "events{} http{ access_log /tmp/edge-access.log; include /etc/nginx/conf.d/*.conf; }\n")
        env = dict(os.environ, PATH=os.path.dirname(NGINX) + ":" + os.environ["PATH"], EDGE_MODE=mode, SITE_NAME=SITE,
                   DOCUSEAL_HOST=SIGN, FRONTEND_UPSTREAM=f"127.0.0.1:{FE_PORT}", DOCUSEAL_UPSTREAM=f"127.0.0.1:{DS_PORT}")
        env.pop("TEMPLATES", None)
        cls.proc = subprocess.Popen(["/bin/sh", os.path.join(EDGE, "edge-run.sh")], env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, preexec_fn=os.setsid)
        for _ in range(50):
            try: socket.create_connection(("127.0.0.1", 8081), 0.2).close(); return
            except OSError: time.sleep(0.2)
        raise RuntimeError("edge did not start: " + cls.proc.stdout.read(2000).decode())

    @classmethod
    def stop(cls):
        if cls.proc:
            os.killpg(os.getpgid(cls.proc.pid), signal.SIGTERM); cls.proc.wait(); cls.proc = None
        subprocess.run(["pkill", "-f", "nginx: master"], check=False); time.sleep(0.5)

    @classmethod
    def setUpClass(cls):
        # edge-run.sh hardcodes the template dir; point it at the repo copy
        os.makedirs("/opt/afaqbridge", exist_ok=True)
        shutil.rmtree("/opt/afaqbridge/templates", ignore_errors=True)
        shutil.copytree(os.path.join(EDGE, "templates"), "/opt/afaqbridge/templates")

    @classmethod
    def tearDownClass(cls):
        cls.stop()


class DevMode(EdgeTests):  # noqa
    @classmethod
    def setUpClass(cls):
        super().setUpClass(); cls.start("dev")

    def test_site_routes_to_frontend_with_forwarding_headers(self):
        r, d = req(SITE, "/app?x=1", headers={"X-Forwarded-For": "6.6.6.6", "X-Forwarded-Proto": "https"})
        j = json.loads(d); h = {k.lower(): v for k, v in j["headers"].items()}
        self.assertEqual((r.status, j["who"], j["path"]), (200, "frontend", "/app?x=1"))
        self.assertEqual(h["host"], SITE)
        self.assertEqual(h["x-forwarded-for"], "127.0.0.1", "client-supplied X-Forwarded-For must be overwritten")
        self.assertEqual(h["x-forwarded-proto"], "http")
        self.assertEqual(h["x-real-ip"], "127.0.0.1")

    def test_docuseal_host_routes_to_docuseal(self):
        self.assertEqual(json.loads(req(SIGN, "/s/abc")[1])["who"], "docuseal")

    def test_unknown_host_is_closed(self):
        with self.assertRaises((http.client.RemoteDisconnected, ConnectionError)):
            req("evil.example", "/")

    def test_websocket_upgrade_reaches_upstream(self):
        s = socket.create_connection(("127.0.0.1", 80), 5)
        s.sendall(f"GET /socket.io/?EIO=4&transport=websocket HTTP/1.1\r\nHost: {SITE}\r\nUpgrade: websocket\r\n"
                  "Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n".encode())
        resp = s.recv(2048).decode().lower(); s.close()
        self.assertIn("101", resp.split("\r\n")[0]); self.assertIn("x-seen-connection: upgrade", resp)

    def test_body_size_limits(self):
        self.assertEqual(req(SITE, "/api/method/x", "POST", body=b"a" * (10 * 1024 * 1024))[0].status, 200)
        self.assertEqual(req(SITE, "/api/method/x", "POST", body=b"a" * (60 * 1024 * 1024))[0].status, 413)

    def test_login_rate_limit(self):
        codes = {req(SITE, "/api/method/login", "POST", body=b"u=1")[0].status for _ in range(80)}
        self.assertIn(429, codes); self.assertIn(200, codes)

    def test_health_endpoint_not_published_via_public_listener(self):
        self.assertEqual(json.loads(req(SITE, "/healthz")[1])["path"], "/healthz")  # proxied to Frappe, not answered by edge
        r, d = req("127.0.0.1", "/healthz", port=8081); self.assertEqual(d, b"ok\n")

    def test_no_server_version_leak(self):
        self.assertNotIn("/", req(SITE)[0].getheader("Server", "nginx"))


class ProdMode(EdgeTests):
    CERT = "/etc/letsencrypt/live/afaqbridge"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        shutil.rmtree("/etc/letsencrypt", ignore_errors=True)
        os.makedirs("/var/www/certbot/.well-known/acme-challenge", exist_ok=True)
        open("/var/www/certbot/.well-known/acme-challenge/tok", "w").write("challenge-ok")

    def test_1_bootstrap_without_certificate_serves_acme_only(self):
        self.start("prod")
        r, d = req(SITE, "/.well-known/acme-challenge/tok"); self.assertEqual((r.status, d), (200, b"challenge-ok"))
        self.assertEqual(req(SITE, "/")[0].status, 503)

    def test_2_with_certificate_redirects_and_terminates_tls(self):
        os.makedirs(self.CERT, exist_ok=True)
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", self.CERT + "/privkey.pem",
                        "-out", self.CERT + "/fullchain.pem", "-days", "1", "-subj", f"/CN={SITE}"], check=True, capture_output=True)
        self.start("prod")
        r, _ = req(SITE, "/app?a=1"); self.assertEqual(r.status, 301); self.assertEqual(r.getheader("Location"), f"https://{SITE}/app?a=1")
        self.assertEqual(req(SITE, "/.well-known/acme-challenge/tok")[0].status, 200)
        r, d = req(SITE, "/", port=443, tls=True); j = json.loads(d)
        self.assertEqual(j["who"], "frontend")
        hsts = r.getheaders(); hsts = [v for k, v in hsts if k.lower() == "strict-transport-security"]
        self.assertEqual(hsts, ["max-age=31536000"], "exactly one HSTS header, without includeSubDomains/preload")
        self.assertEqual({k.lower(): v for k, v in j["headers"].items()}["x-forwarded-proto"], "https")
        self.assertEqual(json.loads(req(SIGN, "/", port=443, tls=True)[1])["who"], "docuseal")
        with self.assertRaises((http.client.RemoteDisconnected, ConnectionError, ssl.SSLError)):
            req("evil.example", "/", port=443, tls=True)


if __name__ == "__main__":
    unittest.main()
