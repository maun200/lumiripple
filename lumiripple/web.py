"""Local web interface.

Binds to 127.0.0.1 only. Every command needs the access token, which is never sent by a browser on its own (no cookies), so
other web sites cannot use the interface. Host and Origin are checked as well, against DNS rebinding.
"""
import hmac
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 17890
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
FILES = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/ui.js": ("ui.js", "text/javascript"),
         "/style.css": ("style.css", "text/css"), "/icon.svg": ("icon.svg", "image/svg+xml")}
MAX_BODY = 1 << 17
DRAIN_LIMIT = 1 << 20


def read_token(path):
    with open(path, encoding="ascii") as f:
        t = f.read().strip()
    if len(t) < 32:
        raise ValueError("the access token is too short")
    return t


def make_token(path):
    """Create the token file (private to its owner) unless it exists."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="ascii") as f:
            f.write(secrets.token_urlsafe(32))
    return read_token(path)


def make_handler(command, token, port):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}

    class Handler(BaseHTTPRequestHandler):
        protocol_version, server_version, sys_version = "HTTP/1.1", "LumiRipple", ""
        timeout = 30

        def log_message(self, *a):
            pass

        def _reply(self, code, body, kind):
            self.send_response(code)
            for k, v in (("Content-Type", f"{kind}; charset=utf-8"), ("Content-Length", str(len(body))), ("Cache-Control", "no-store"),
                         ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                         ("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, data):
            if code != 200:
                self.close_connection = True        # the body may be unread
                self._drain()
            self._reply(code, json.dumps(data).encode(), "application/json")

        def _drain(self):
            # Read a refused body before answering. Closing with unread data makes some systems (macOS)
            # reset the connection, and the client never sees the answer. Very large bodies are not read.
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return
            if 0 < n <= DRAIN_LIMIT:
                while n > 0:
                    got = self.rfile.read(min(n, 65536))
                    if not got:
                        break
                    n -= len(got)

        def _allowed(self):
            return self.headers.get("Host") in hosts and self.headers.get("Origin") in (None, *origins)

        def do_GET(self):
            f = FILES.get(self.path.split("?")[0])
            if not self._allowed() or not f:
                return self._json(404, {"ok": False, "error": "not found"})
            with open(os.path.join(STATIC, f[0]), "rb") as h:
                self._reply(200, h.read(), f[1])

        def do_POST(self):
            if not self._allowed() or self.path != "/api":
                return self._json(404, {"ok": False, "error": "not found"})
            sent = self.headers.get("Authorization", "")
            if not hmac.compare_digest(sent.encode("latin-1", "replace"), b"Bearer " + token.encode()):
                return self._json(401, {"ok": False, "error": "wrong access token"})
            if self.headers.get_content_type() != "application/json":
                return self._json(415, {"ok": False, "error": "JSON expected"})
            try:
                n = int(self.headers.get("Content-Length", ""))
            except ValueError:
                n = -1
            if not 0 <= n <= MAX_BODY:
                return self._json(413, {"ok": False, "error": "request too large"})
            try:
                b = json.loads(self.rfile.read(n))
            except ValueError:
                b = None
            self._json(200, command(b))
    return Handler


def serve(command, token, port=PORT):
    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = os.name != "nt"       # on Windows this would allow a second server on the same port
    s = Server(("127.0.0.1", port), make_handler(command, token, port))
    if port == 0:
        s.RequestHandlerClass = make_handler(command, token, s.server_address[1])
    threading.Thread(target=s.serve_forever, daemon=True, name="web").start()
    return s
