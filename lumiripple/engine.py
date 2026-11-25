"""The loop: connects to OpenRGB servers, renders frames and keeps time for the core."""
import json
import os
import select
import sys
import threading
import time
import urllib.request

from . import effects, openrgb, stats

FPS = 33


class OpenLinkHub:
    """OpenLinkHub owns Corsair keyboards and only accepts frames while its OpenRGB integration is on."""

    def __init__(self, base="http://127.0.0.1:27003"):
        self.base = base

    def integration(self, serial, on):
        r = urllib.request.Request(f"{self.base}/api/color/setOpenRgbIntegration",
                                   json.dumps({"deviceId": serial, "mode": int(on)}).encode(),   # only "mode" is evaluated
                                   {"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=5) as a:
            if json.load(a).get("status") != 1:
                raise OSError("OpenLinkHub refused the OpenRGB integration")


class Link:
    """One OpenRGB server with its keyboards."""

    def __init__(self, address, olh):
        self.address, self.olh, self.client, self.boards, self.retry, self.error = address, olh, None, [], 0.0, None

    def open(self):
        self.client = openrgb.Client(*self.address)
        self._read()

    def _read(self):
        self.boards = []
        for dev, c in self.client.keyboards():
            b = openrgb.Board(c)
            if b.description.startswith("OpenLinkHub"):
                self.olh.integration(b.serial, True)
            else:
                self.client.custom_mode(dev)
            self.boards.append((dev, b))

    def poll(self):
        while select.select([self.client], [], [], 0)[0]:
            self.client.read()
        if self.client.take_changed():
            self._read()
            return True
        return False

    def close(self, restore=False):
        for _, b in self.boards if restore else ():
            if b.description.startswith("OpenLinkHub"):
                try:
                    self.olh.integration(b.serial, False)
                except OSError:
                    pass
        if self.client:
            self.client.close()
        self.client, self.boards = None, []


class Engine:
    def __init__(self, core, servers, demo=False, olh=None):
        self.core, self.lock, self.wake, self.stopping = core, threading.RLock(), threading.Event(), False
        self.links = [] if demo else [Link(a, olh or OpenLinkHub()) for a in servers]
        self.demo = openrgb.demo_board() if demo else None
        self.plans, self.last, self.repaint, self.frames = {}, {}, [], {}
        self.meter, self.measure_at, self.save_at, self.said = stats.Meter(), 0.0, None, None

    # ---- called from other threads ----------------------------------------
    def command(self, b):
        with self.lock:
            if isinstance(b, dict) and b.get("cmd") == "frame":
                return {"ok": True, "keys": self._preview()}
            out = self.core.command(b)
        self.wake.set()
        return out

    def on_key(self, name, token, down):
        with self.lock:
            self.core.key(name, token, down, time.monotonic())
        self.wake.set()

    def on_lost(self):
        with self.lock:
            self.core.release_all(time.monotonic())

    def on_status(self, ok, reason):
        with self.lock:
            self.core.status["input"] = ok
            self.core.status["error"] = reason

    # ---- loop --------------------------------------------------------------
    def _boards(self):
        return [(None, None, self.demo)] if self.demo else [(ln, dev, b) for ln in self.links for dev, b in ln.boards]

    def _preview(self):
        for (_, _, b) in self._boards()[:1]:
            f = self.frames.get(id(b))
            if f:
                out = {n: f[i[0]] for n, i in b.by_key.items()}
                out.update({f"+{n}": f[i[0]] for n, i in b.extras.items()})
                return out
        return {}

    def _say(self, text):
        if text != self.said:
            self.said = text
            print(text, flush=True)

    def _connect(self, now):
        for ln in self.links:
            try:
                if ln.client is None:
                    if now < ln.retry:
                        continue
                    ln.retry = now + 3
                    ln.open()
                    self._say(f"connected to {ln.address[0]}:{ln.address[1]}, keyboards: "
                              f"{', '.join(b.name for _, b in ln.boards) or 'none'}")
                    self._repaint(now)
                elif ln.poll():
                    self._repaint(now)
            except (OSError, ValueError, IndexError) as e:
                ln.close()
                ln.error = str(e)
        self.core.status["openrgb"] = bool(self.demo) or any(ln.client for ln in self.links)
        self.core.boards = [b for _, _, b in self._boards()]

    def _repaint(self, now):
        """Servers may blank the keyboard after a change, so paint again a little later, too."""
        self.last.clear()
        self.repaint = [now + .2, now + .5, now + 1]

    def step(self, now):
        c = self.core
        self._connect(now)
        if now >= self.measure_at:
            self.measure_at = now + 1
            for k, v in self.meter.read().items():
                setattr(c.state, k, v)
        c.tick(now)
        if c.dirty and self.save_at is None:
            self.save_at = now + 1
        if self.save_at and now >= self.save_at:
            self.save_at = None
            c.save()
        while self.repaint and now >= self.repaint[0]:
            self.repaint.pop(0)
            self.last.clear()
        for ln, dev, b in self._boards():
            key = (id(b), c.changes, c.active)
            if self.plans.get(id(b), (None,))[0] != key:
                old = self.plans.get(id(b), (None, None))[1]
                self.plans[id(b)] = (key, effects.make_plan(c.e, b, old))
            f = effects.render(b, c.e, c.state, now, self.plans[id(b)][1])
            self.frames[id(b)] = f
            if self.last.get(id(b)) != f:
                self.last[id(b)] = f
                if ln:
                    try:
                        ln.client.update(dev, f)
                    except OSError:
                        ln.close()
        if len(self.plans) > 16:                    # forget boards that are gone
            alive = {id(b) for _, _, b in self._boards()}
            for d in (self.plans, self.last, self.frames):
                for k in [k for k in d if k not in alive]:
                    del d[k]
        wait = min([1.0, self.measure_at - now, *[t - now for t in self.repaint[:1]]] + ([c.due(now)] if c.due(now) is not None else []))
        if effects.animated(c.state, c.e, now):
            wait = min(wait, 1 / FPS)
        return max(wait, 0.001)

    def run(self):
        while not self.stopping:
            t = time.monotonic()
            with self.lock:
                wait = self.step(t)
            self.wake.wait(wait)
            self.wake.clear()
            rest = t + 1 / FPS - time.monotonic()   # key storms must not exceed the frame rate
            if rest > 0 and not self.core.player.active:
                time.sleep(rest)
        with self.lock:
            self.core.player.abort()
            if self.core.dirty:
                self.core.save()
            for ln in self.links:
                ln.close(restore=True)

    def stop(self):
        self.stopping = True
        self.wake.set()


def state_dir():
    if os.environ.get("STATE_DIRECTORY"):           # set by systemd
        return os.environ["STATE_DIRECTORY"].split(":")[0]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    d = os.path.join(base, "lumiripple")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d
