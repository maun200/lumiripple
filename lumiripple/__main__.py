"""Command line: run, helper, open, doctor."""
import argparse
import json
import os
import signal
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

from . import __version__, core, engine, helper, inputs, openrgb, web

SERVERS = [("127.0.0.1", 6742), ("127.0.0.1", 6743)]


def token_path():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "lumiripple", "token")


def service_token(a):
    if a.token_file:
        return web.read_token(a.token_file)
    if os.environ.get("CREDENTIALS_DIRECTORY"):     # systemd LoadCredential
        return web.read_token(os.path.join(os.environ["CREDENTIALS_DIRECTORY"], "token"))
    return web.make_token(token_path())


def address(text):
    host, _, port = text.rpartition(":")
    return host or "127.0.0.1", int(port)


def remote(port, token):
    def call(cmd, **kw):
        r = urllib.request.Request(f"http://127.0.0.1:{port}/api", json.dumps({"cmd": cmd, **kw}).encode(),
                                   {"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(r, timeout=5) as a:
            return json.load(a)
    return call


def run(a):
    token = service_token(a)
    back = inputs.NoInput("demo mode: no key input") if a.demo else inputs.backend()
    eng = engine.Engine(core.Core(a.state or engine.state_dir(), back), a.server or SERVERS, demo=a.demo)
    try:
        web.serve(eng.command, token, a.port)
    except OSError as e:
        sys.exit(f"cannot open port {a.port}: {e} (is LumiRipple already running?)")
    back.start(eng.on_key, eng.on_lost, eng.on_status)
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: eng.stop())
    h = None
    if not a.no_helper:
        h = helper.Helper(lambda cmd, **kw: eng.command({"cmd": cmd, **kw}))
        threading.Thread(target=h.run, daemon=True, name="helper").start()
    print(f"LumiRipple {__version__}: http://127.0.0.1:{a.port}/  (open it with: lumiripple open)", flush=True)
    try:
        eng.run()
    finally:
        if h:
            h.stop()
        back.stop()


def run_helper(a):
    h = helper.Helper(remote(a.port, web.make_token(token_path())))
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: h.stop())
    h.run()


def open_ui(a):
    url = f"http://127.0.0.1:{a.port}/#{web.make_token(token_path())}"     # the part after # never leaves the browser
    if a.print or not webbrowser.open(url):
        print(url)


def doctor(a):
    """Shows what works and what does not. Prints nothing private."""
    print(f"LumiRipple {__version__} on {sys.platform}, Python {sys.version.split()[0]}")
    for host, port in a.server or SERVERS:
        try:
            c = openrgb.Client(host, port)
            found = [openrgb.Board(x) for _, x in c.keyboards()]
            c.close()
            print(f"[ok]   OpenRGB server on {host}:{port}, protocol {c.version}, per-key keyboards: {len(found)}")
            for b in found:
                print(f"         {b.name}: {len(b.leds)} LEDs, {len(b.by_key)} named keys, other lights: {', '.join(b.extras) or 'none'}")
        except OSError as e:
            print(f"[--]   no OpenRGB server on {host}:{port} ({e})")
    if sys.platform.startswith("linux"):
        kb = inputs.LinuxInput.keyboards()
        print(f"[info] keyboards seen by the kernel: {len(kb)}, readable by this user: {sum(os.access(p, os.R_OK) for p in kb)}"
              " (the service may read them even if you may not)")
    print(f"[{'ok' if helper.np is not None else '--'}]   numpy (needed for sound): {'yes' if helper.np is not None else 'missing'}")
    try:
        g = remote(a.port, web.read_token(token_path()))("get")
        print("[ok]   service answers:", json.dumps(g.get("status")))
    except (OSError, ValueError) as e:
        print("[--]   service does not answer:", e)


def main(argv=None):
    p = argparse.ArgumentParser(prog="lumiripple", description="Reactive per-key keyboard lighting for OpenRGB")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="what", required=True)
    for name, fn, text in (("run", run, "run the service"), ("helper", run_helper, "run only the sound and GPU helper"),
                           ("open", open_ui, "open the settings in the browser"), ("doctor", doctor, "check the setup")):
        q = sub.add_parser(name, help=text)
        q.set_defaults(fn=fn)
        q.add_argument("--port", type=int, default=web.PORT)
        if name in ("run", "doctor"):
            q.add_argument("--server", type=address, action="append", metavar="HOST:PORT", help="OpenRGB server (repeatable)")
        if name == "run":
            q.add_argument("--demo", action="store_true", help="virtual keyboard, no hardware needed")
            q.add_argument("--no-helper", action="store_true", help="sound and GPU come from a separate helper")
            q.add_argument("--state", help="folder for settings")
            q.add_argument("--token-file")
        if name == "open":
            q.add_argument("--print", action="store_true", help="only print the address")
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
