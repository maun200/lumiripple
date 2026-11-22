import http.client
import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest

from lumiripple import core, engine, inputs, openrgb, web


def s(t):
    b = t.encode()
    return struct.pack("<H", len(b) + 1) + b + b"\0"


def device(version, leds, typ=5, description="test"):
    k = struct.pack("<i", typ) + s("Board") + (s("Vendor") if version >= 1 else b"") + s(description) + s("1") + s("SER1") + s("loc")
    k += struct.pack("<Hi", 2, 0)
    for n in ("Direct", "Static"):
        k += s(n) + struct.pack(f"<{12 if version >= 3 else 9}I", *range(12 if version >= 3 else 9)) + struct.pack("<H", 1) + b"\1\2\3\0"
    k += struct.pack("<H", 1) + s("Keyboard") + struct.pack("<4I", 2, len(leds), len(leds), len(leds))
    k += struct.pack("<H", 8 + 4 * len(leds)) + struct.pack("<2I", 1, len(leds)) + struct.pack(f"<{len(leds)}I", *range(len(leds)))
    if version >= 4:
        k += struct.pack("<H", 1) + s("seg") + struct.pack("<iII", 1, 0, 2)
    k += struct.pack("<H", len(leds)) + b"".join(s(n) + struct.pack("<I", 0) for n in leds) + struct.pack("<H", len(leds)) + b"\0" * 4 * len(leds)
    return struct.pack("<I", len(k) + 4) + k


LEDS = [f"Key: {c}" for c in "QWERTYUIOPASDFGHJKLZXCVBNM"] + ["Logo"]


class FakeServer(threading.Thread):
    def __init__(self, version=4, devices=None):
        super().__init__(daemon=True)
        self.version, self.devices = version, devices
        self.srv = socket.create_server(("127.0.0.1", 0))
        self.port, self.frames, self.modes, self.c = self.srv.getsockname()[1], [], [], None
        self.start()

    def note(self):
        self.c.sendall(b"ORGB" + struct.pack("<III", 0, 100, 0))

    def run(self):
        while True:
            self.c, _ = self.srv.accept()
            f = self.c.makefile("rb")
            try:
                while len(h := f.read(16)) == 16:
                    dev, op, n = struct.unpack("<III", h[4:])
                    body = f.read(n)
                    out = None
                    if op == 40:
                        out = struct.pack("<I", self.version)
                    elif op == 0:
                        out = struct.pack("<I", len(self.list()))
                    elif op == 1:
                        self.note()                 # a notification in the middle of an answer
                        out = self.list()[dev]
                    elif op == 1100:
                        self.modes.append(dev)
                    elif op == 1050:
                        self.frames.append((dev, body))
                    if out is not None:
                        self.c.sendall(b"ORGB" + struct.pack("<III", dev, op, len(out)) + out)
            except OSError:
                pass

    def list(self):
        v = min(self.version, 4)
        return self.devices or [device(v, ["A", "B"], typ=0), device(v, LEDS)]


class ClientTest(unittest.TestCase):
    def test_every_protocol_version(self):
        for v in (1, 2, 3, 4, 5, 6):
            c = openrgb.Client(port=FakeServer(v).port)
            self.assertEqual(c.version, min(v, 4))
            kb = c.keyboards()
            self.assertEqual([(i, d["name"], len(d["leds"])) for i, d in kb], [(1, "Board", 27)], v)
            self.assertEqual(kb[0][1]["modes"], ["Direct", "Static"])
            self.assertTrue(c.take_changed())
            c.close()

    def test_truncated_data_is_skipped_not_fatal(self):
        good = device(4, LEDS)
        for cut in (3, 20, 60, len(good) // 2):
            c = openrgb.Client(port=FakeServer(4, [good[:cut], good]).port)
            self.assertEqual([i for i, _ in c.keyboards()], [1], cut)
            c.close()

    def test_frame_bytes(self):
        srv = FakeServer()
        c = openrgb.Client(port=srv.port)
        c.update(1, [(1, 2, 3), (4, 5, 6)])
        time.sleep(.2)
        self.assertEqual(srv.frames, [(1, struct.pack("<IH", 14, 2) + bytes([1, 2, 3, 0, 4, 5, 6, 0]))])


class FakeOlh:
    def __init__(self):
        self.calls = []

    def integration(self, serial, on):
        self.calls.append((serial, on))


class EngineTest(unittest.TestCase):
    def start(self, srv, olh=None):
        e = engine.Engine(core.Core(tempfile.mkdtemp(), inputs.NoInput()), [("127.0.0.1", srv.port)], olh=olh or FakeOlh())
        t = threading.Thread(target=e.run, daemon=True)
        t.start()
        self.addCleanup(lambda: (e.stop(), t.join(3)))
        return e, t

    def wait(self, cond, seconds=6):
        end = time.time() + seconds
        while time.time() < end and not cond():
            time.sleep(.02)
        self.assertTrue(cond())

    def test_connects_paints_reacts_and_reconnects(self):
        srv = FakeServer()
        e, _ = self.start(srv)
        self.wait(lambda: srv.frames)
        self.assertEqual((srv.modes[:1], srv.frames[0][0]), ([1], 1))
        time.sleep(1.5)
        n = len(srv.frames)
        e.on_key("A", 30, True)
        self.wait(lambda: len(srv.frames) > n + 5)
        self.assertIn("A", e.command({"cmd": "frame"})["keys"])
        srv.c.shutdown(socket.SHUT_RDWR)
        n = len(srv.frames)
        self.wait(lambda: len(srv.frames) > n and e.core.status["openrgb"], 10)

    def test_frame_rate_is_limited(self):
        srv = FakeServer()
        e, _ = self.start(srv)
        self.wait(lambda: srv.frames)
        n, t = len(srv.frames), time.time()
        while time.time() < t + 2:
            e.on_key("A", 30, True)
            e.on_key("A", 30, False)
            time.sleep(.001)
        self.assertLess((len(srv.frames) - n) / 2, 40)

    def test_openlinkhub_is_switched_on_and_back(self):
        olh, srv = FakeOlh(), FakeServer(4, [device(4, LEDS, description="OpenLinkHub Backend Device")])
        e, t = self.start(srv, olh)
        self.wait(lambda: srv.frames)
        self.assertEqual(olh.calls[0], ("SER1", True))
        e.stop()
        t.join(3)
        self.assertEqual(olh.calls[-1], ("SER1", False))

    def test_runs_without_any_server(self):
        e = engine.Engine(core.Core(tempfile.mkdtemp(), inputs.NoInput()), [("127.0.0.1", 1)])
        self.assertGreater(e.step(1.0), 0)
        self.assertFalse(e.core.status["openrgb"])


class WebTest(unittest.TestCase):
    TOKEN = "t" * 43

    def setUp(self):
        self.srv = web.serve(lambda b: {"ok": True, "got": b}, self.TOKEN, 0)
        self.port = self.srv.server_address[1]
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def ask(self, method="POST", path="/api", body=b'{"cmd": "x"}', **headers):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Authorization": f"Bearer {self.TOKEN}", "Content-Type": "application/json", **{k.replace("_", "-"): v for k, v in headers.items()}}
        c.request(method, path, body, {k: v for k, v in h.items() if v is not None})
        r = c.getresponse()
        out = r.status, r.read(), dict(r.getheaders())
        c.close()
        return out

    def test_good_request(self):
        code, body, _ = self.ask()
        self.assertEqual((code, json.loads(body)["got"]), (200, {"cmd": "x"}))

    def test_bad_requests(self):
        for want, kw in ((401, dict(Authorization=None)), (401, dict(Authorization="Bearer wrong")), (401, dict(Authorization="Bearer ")), (404, dict(Host="evil.example")),
                         (404, dict(Host=f"evil.example:{self.port}")), (404, dict(Origin="http://evil.example")), (404, dict(Origin="null")), (404, dict(path="/api/../x")),
                         (415, dict(Content_Type="text/plain")), (413, dict(body=b"x" * 200000)), (404, dict(method="GET", path="/../config.py")), (404, dict(method="GET", path="/config.py"))):
            self.assertEqual(self.ask(**kw)[0], want, kw)

    def test_broken_json_reaches_the_core_as_none(self):
        self.assertIsNone(json.loads(self.ask(body=b"{broken")[1])["got"])

    def test_pages_and_headers(self):
        for path, kind in (("/", "text/html"), ("/app.js", "text/javascript"), ("/ui.js", "text/javascript"), ("/style.css", "text/css"), ("/icon.svg", "image/svg+xml")):
            code, body, h = self.ask("GET", path, None, Authorization=None)
            self.assertEqual(code, 200, path)
            self.assertTrue(h["Content-Type"].startswith(kind) and "frame-ancestors 'none'" in h["Content-Security-Policy"])
            self.assertNotIn(self.TOKEN.encode(), body)
        self.assertNotIn(b"<script>", self.ask("GET", "/", None)[1])

    def test_only_loopback(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")

    def test_token_file(self):
        p = os.path.join(tempfile.mkdtemp(), "a", "token")
        t = web.make_token(p)
        self.assertEqual((t, len(t) >= 32), (web.make_token(p), True))
        if os.name == "posix":
            self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
