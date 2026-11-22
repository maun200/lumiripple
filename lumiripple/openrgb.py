"""OpenRGB SDK client (protocol 0-4) and the board model built from what the server reports."""
import socket
import struct

from . import keys

KEYBOARD = 5
REQ_COUNT, REQ_DATA, REQ_VERSION, SET_NAME, LIST_UPDATED = 0, 1, 40, 50, 100
UPDATE_LEDS, CUSTOM_MODE = 1050, 1100
MAX_PROTOCOL = 4
NONE = 0xFFFFFFFF


class Reader:
    def __init__(self, data):
        self.d, self.p = data, 0

    def get(self, fmt):
        v = struct.unpack_from("<" + fmt, self.d, self.p)
        self.p += struct.calcsize("<" + fmt)
        return v[0] if len(v) == 1 else v

    def text(self):
        n = self.get("H")
        self.p += n
        return self.d[self.p - n:self.p].rstrip(b"\0").decode("utf-8", "replace")


def parse(data, version):
    """Controller data block -> dict. Raises struct.error on truncated data."""
    r = Reader(data)
    r.get("I")
    c = {"type": r.get("i"), "name": r.text(), "vendor": r.text() if version >= 1 else "", "description": r.text()}
    c["version"], c["serial"], c["location"] = r.text(), r.text(), r.text()
    modes, c["active"], c["modes"] = r.get("H"), r.get("i"), []
    for _ in range(modes):
        name = r.text()
        r.p += 4 * (12 if version >= 3 else 9)
        n = r.get("H")
        r.p += 4 * n
        c["modes"].append(name)
    c["zones"] = []
    for _ in range(r.get("H")):
        z = {"name": r.text(), "type": r.get("i")}
        r.get("II")
        z["leds"], size, z["matrix"] = r.get("I"), r.get("H"), None
        if size >= 8:
            h, w = r.get("II")
            cells = r.get(f"{h * w}I") if h * w > 1 else ((r.get("I"),) if h * w else ())
            z["matrix"] = [list(cells[y * w:(y + 1) * w]) for y in range(h)]
        if version >= 4:
            for _ in range(r.get("H")):
                r.text()
                r.get("iII")
        c["zones"].append(z)
    c["leds"] = []
    for _ in range(r.get("H")):
        c["leds"].append(r.text())
        r.get("I")
    return c


class Board:
    """LEDs of one keyboard: canonical key name (or None), position and lookup tables."""

    def __init__(self, c):
        self.name, self.vendor, self.serial, self.description = c["name"], c["vendor"], c["serial"], c["description"]
        cells, start = {}, 0
        for z in c["zones"]:
            for y, row in enumerate(z["matrix"] or ()):
                for x, v in enumerate(row):
                    if v != NONE and v < z["leds"]:
                        cells.setdefault(start + v, (x, y))
            start += z["leds"]
        raw = [n[5:] if n.startswith("Key: ") else None for n in c["leds"]]
        self.leds = [self._canonical(n, raw, cells) for n in raw]
        self.labels = raw
        self.pos, width = {}, max((x for x, _ in cells.values()), default=0) or 1
        for i, n in enumerate(self.leds):
            if n in keys.BY_NAME:
                k = keys.BY_NAME[n]
                self.pos[i] = (k.x + k.w / 2, k.y + k.h / 2)
            elif i in cells:                        # unknown key or light bar: use the matrix cell
                x, y = cells[i]
                self.pos[i] = (x * 22.5 / width + .5, y * 1.05 + .5)
        self.by_key = {}
        for i, n in enumerate(self.leds):
            if n:
                self.by_key.setdefault(n, []).append(i)
        self.extras, used = {}, {}
        for i, full in enumerate(c["leds"]):
            if self.leds[i] not in keys.BY_NAME:
                label = full.removeprefix("Key: ").strip() or "Light"
                used[label] = used.get(label, 0) + 1
                self.extras.setdefault(label if used[label] == 1 or label != "Light" else f"Light {used[label]}", []).append(i)
        self.rows = [[n for n in row if n in self.by_key] for row in keys.rows()]
        self.rows = [r for r in self.rows if r]

    @staticmethod
    def _canonical(n, raw, cells):
        """Cap label -> physical key. Layouts are recognised by where Z/Y and A/Q sit in the matrix."""
        if n is None:
            return None
        def row(label):
            return cells.get(raw.index(label), (0, -1))[1] if label in raw else -1
        if -1 < row("Z") < row("Y"):                # QWERTZ
            n = {"Z": "Y", "Y": "Z"}.get(n, n)
        elif -1 < row("A") < row("Q"):              # AZERTY
            n = {"A": "Q", "Q": "A", "Z": "W", "W": "Z", "M": ";", ",": "M", ";": ",", ":": ".", "!": "/", ")": "-"}.get(n, n)
        if n in keys.BY_NAME:
            return n
        return keys.ALIASES.get(n, n)

    def label(self, name):
        i = self.by_key.get(name)
        return self.labels[i[0]] if i else name


class Client:
    def __init__(self, host="127.0.0.1", port=6742, timeout=3):
        self.s = socket.create_connection((host, port), timeout)
        self.changed = False
        try:
            self._send(0, REQ_VERSION, struct.pack("<I", MAX_PROTOCOL))
            try:
                self.version = min(struct.unpack("<I", self._answer(REQ_VERSION)[:4])[0], MAX_PROTOCOL)
            except TimeoutError:                    # servers before protocol 1 do not answer
                self.version = 0
            self._send(0, SET_NAME, b"LumiRipple\0")
        except BaseException:
            self.close()
            raise

    def fileno(self):
        return self.s.fileno()

    def close(self):
        self.s.close()

    def _exact(self, n):
        b = b""
        while len(b) < n:
            part = self.s.recv(n - len(b))
            if not part:
                raise ConnectionError("the OpenRGB server closed the connection")
            b += part
        return b

    def _packet(self):
        head = self._exact(16)
        dev, op, n = struct.unpack("<III", head[4:])
        if head[:4] != b"ORGB" or n > 1 << 22:
            raise ConnectionError("unexpected data from the OpenRGB server")
        body = self._exact(n)
        if op == LIST_UPDATED:
            self.changed = True
        return dev, op, body

    def _send(self, dev, op, body=b""):
        self.s.sendall(b"ORGB" + struct.pack("<III", dev, op, len(body)) + body)

    def _answer(self, op):
        while True:
            _, got, body = self._packet()
            if got == op:
                return body

    def read(self):
        """Call when data is waiting."""
        self._packet()

    def take_changed(self):
        c, self.changed = self.changed, False
        return c

    def keyboards(self):
        """[(device index, controller dict)] for every keyboard with named per-key LEDs."""
        self._send(0, REQ_COUNT)
        n = struct.unpack("<I", self._answer(REQ_COUNT)[:4])[0]
        out = []
        for i in range(min(n, 256)):
            body = struct.pack("<I", self.version) if self.version else b""
            self._send(i, REQ_DATA, body)
            try:
                c = parse(self._answer(REQ_DATA), self.version)
            except (struct.error, IndexError):
                continue
            if c["type"] == KEYBOARD and sum(x.startswith("Key: ") for x in c["leds"]) >= 20:
                out.append((i, c))
        return out

    def custom_mode(self, dev):
        self._send(dev, CUSTOM_MODE)

    def update(self, dev, colors):
        body = b"".join(bytes((*c, 0)) for c in colors)
        self._send(dev, UPDATE_LEDS, struct.pack("<IH", 6 + len(body), len(colors)) + body)


def demo_board():
    """A virtual full-size board, for trying the interface without hardware."""
    n = [k.name for k in keys.KEYS if k.name not in ("Right Windows", "\\ (ISO)", "#")]
    return Board({"name": "Demo keyboard", "vendor": "LumiRipple", "serial": "", "description": "virtual",
                  "zones": [{"matrix": None, "leds": len(n) + 1}], "leds": [f"Key: {x}" for x in n] + ["Logo"]})
