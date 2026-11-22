"""Key input and macro output. Linux talks to the kernel directly; Windows and macOS use pynput."""
import glob
import os
import selectors
import struct
import sys
import threading
import time

from . import keys

_EVENT = struct.Struct("llHHi")
EV_SYN, EV_KEY = 0, 1


class NoInput:
    """Used when key input is unavailable (or in demo mode): lighting still works."""
    sees_own_events = False

    def __init__(self, reason=None):
        self.reason = reason

    def start(self, on_key, on_lost, on_status):
        on_status(False, self.reason)

    def send(self, token, down):
        pass

    def label(self, token):
        return str(token)

    def stop(self):
        pass


class LinuxInput:
    """Reads every real keyboard under /dev/input (never grabs it) and types macros through /dev/uinput."""
    sees_own_events = False

    def __init__(self):
        self.stopping, self.ui = threading.Event(), None

    @staticmethod
    def keyboards():
        out = []
        for d in glob.glob("/sys/class/input/event*"):
            if "/virtual/" in os.path.realpath(d):  # on-screen keyboards, remappers and our own macro device
                continue
            try:
                with open(d + "/device/capabilities/key") as f:
                    words = f.read().split()
            except OSError:
                continue
            bits = 0
            for w in words:
                bits = bits << (struct.calcsize("l") * 8) | int(w, 16)
            if all(bits >> c & 1 for c in (16, 30, 44, 57, 28)):      # Q, A, Z, space and enter
                out.append("/dev/input/" + os.path.basename(d))
        return out

    def start(self, on_key, on_lost, on_status):
        self.on = on_key, on_lost, on_status
        self._open_uinput()
        threading.Thread(target=self._loop, daemon=True, name="input").start()

    def _loop(self):
        on_key, on_lost, on_status = self.on
        sel, open_ = selectors.DefaultSelector(), {}
        told, scan = None, 0.0
        while not self.stopping.is_set():
            if time.monotonic() >= scan:
                scan, error = time.monotonic() + 2, None
                for path in self.keyboards():
                    if path not in open_.values():
                        try:
                            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                        except OSError as e:
                            error = f"cannot read {path}: {e.strerror}"
                            continue
                        open_[fd] = path
                        sel.register(fd, selectors.EVENT_READ)
                now = (bool(open_), None if open_ else error or "no keyboard found")
                if now != told:
                    told = now
                    on_status(*now)
            if not open_:
                self.stopping.wait(.5)
                continue
            for k, _ in sel.select(.5):
                try:
                    data = os.read(k.fd, _EVENT.size * 64)
                except BlockingIOError:
                    continue
                except OSError:                     # unplugged
                    sel.unregister(k.fd)
                    os.close(k.fd)
                    del open_[k.fd]
                    on_lost()
                    scan = 0.0
                    continue
                for i in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
                    _, _, typ, code, value = _EVENT.unpack_from(data, i)
                    if typ == EV_KEY and value in (0, 1):
                        on_key(keys.EVDEV.get(code), code, bool(value))
        for fd in open_:
            os.close(fd)

    def _open_uinput(self):
        import fcntl
        try:
            fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
            fcntl.ioctl(fd, 0x40045564, EV_KEY)                        # UI_SET_EVBIT
            for code in range(1, 249):
                fcntl.ioctl(fd, 0x40045565, code)                      # UI_SET_KEYBIT
            os.write(fd, struct.pack("80sHHHHI", b"LumiRipple macros", 6, 0, 0, 1, 0) + b"\0" * (4 * 64 * 4))
            fcntl.ioctl(fd, 0x5501)                                    # UI_DEV_CREATE
            self.ui = fd
        except OSError:
            self.ui = None

    def send(self, token, down):
        if self.ui is not None and type(token) is int and 0 < token < 249:
            os.write(self.ui, _EVENT.pack(0, 0, EV_KEY, token, int(down)) + _EVENT.pack(0, 0, EV_SYN, 0, 0))

    def label(self, token):
        return keys.EVDEV.get(token, f"key {token}")

    def stop(self):
        self.stopping.set()
        if self.ui is not None:
            os.close(self.ui)                       # closing destroys the device
            self.ui = None


class PynputInput:
    """Windows and macOS. Tokens are strings: 'vk:65', 'char:a' or 'key:shift'."""
    sees_own_events = True

    def __init__(self):
        from pynput import keyboard
        self.kb, self.out, self.listener = keyboard, keyboard.Controller(), None

    def start(self, on_key, on_lost, on_status):
        scan = {}

        def win_filter(msg, data):
            scan["code"] = data.scanCode | (0x100 if data.flags & 1 else 0)
            return True

        def name_of(key):
            if sys.platform == "win32" and "code" in scan:
                return keys.WIN_SCAN.get(scan["code"])
            vk = getattr(key, "vk", None)
            if vk is None and isinstance(key, self.kb.Key):
                vk = key.value.vk
            return keys.MAC.get(vk) if sys.platform == "darwin" else None
        extra = {"win32_event_filter": win_filter} if sys.platform == "win32" else {}
        self.listener = self.kb.Listener(on_press=lambda k: on_key(name_of(k), self._token(k), True),
                                         on_release=lambda k: on_key(name_of(k), self._token(k), False), **extra)
        self.listener.start()
        trusted = getattr(self.listener, "IS_TRUSTED", True)
        on_status(bool(trusted), None if trusted else
                  "macOS blocks key input: allow it under Privacy & Security > Accessibility and Input Monitoring")

    def _token(self, k):
        if isinstance(k, self.kb.Key):
            return f"key:{k.name}"
        return f"vk:{k.vk}" if getattr(k, "vk", None) is not None else f"char:{k.char}"

    def _key(self, token):
        kind, _, v = token.partition(":")
        return {"key": lambda: self.kb.Key[v], "vk": lambda: self.kb.KeyCode.from_vk(int(v)),
                "char": lambda: self.kb.KeyCode.from_char(v)}[kind]()

    def send(self, token, down):
        try:
            (self.out.press if down else self.out.release)(self._key(token))
        except (KeyError, ValueError, AttributeError, self.kb.Controller.InvalidKeyException):
            pass

    def label(self, token):
        return token.partition(":")[2]

    def stop(self):
        if self.listener:
            self.listener.stop()


def backend():
    if sys.platform.startswith("linux"):
        return LinuxInput()
    try:
        return PynputInput()
    except ImportError:
        return NoInput("the Python package pynput is missing")
