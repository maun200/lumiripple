"""Building blocks of all effects: control descriptions, keyboard geometry and the Pattern class."""
import copy
import math

from .. import config


def dim(x, h):
    """A color value of 1 or more never dims below 1: an LED at 0 looks brighter than a very dim one, because the
    neighbouring keys shine into it. Only brightness 0 switches off; fades below 1 still run down to 0."""
    return x * h if x < 1 or h <= 0 else max(1.0, x * h)


class Control:
    kind = ""

    def __init__(self, name, title, default):
        self.name, self.title, self.default = name, title, default

    def check(self, v):
        raise NotImplementedError

    def describe(self):
        return {"kind": self.kind, "name": self.name, "title": self.title, "default": copy.deepcopy(self.default)}


class Color(Control):
    """paint: None = one color only, "area" or "wave" = also a gradient (as in the color dialog)."""
    kind = "color"

    def __init__(self, name, title, default, paint=None, warning=None):
        super().__init__(name, title, default)
        self.paint, self.warning = paint, warning

    def check(self, v):
        return config.is_paint(v) if self.paint else config.is_color(v)

    def describe(self):
        d = {**super().describe(), "paint": self.paint or "solid"}
        return {**d, "warning": self.warning} if self.warning else d


class Number(Control):
    kind = "number"

    def __init__(self, name, title, lo, hi, default, step, unit="", zero=None):
        """zero: text the interface shows for the value 0 (e.g. "still")."""
        super().__init__(name, title, default)
        self.lo, self.hi, self.step, self.unit, self.zero = lo, hi, step, unit, zero

    def check(self, v):
        return type(v) in (int, float) and math.isfinite(v) and self.lo <= v <= self.hi

    def snap(self, v):
        """To the nearest allowed step; whole-number steps give an int (counts must be whole)."""
        x = min(max(self.lo + round((v - self.lo) / self.step) * self.step, self.lo), self.hi)
        if float(self.step).is_integer() and float(self.lo).is_integer():
            return int(round(x))
        digits = max(0, -math.floor(math.log10(self.step) + 1e-9)) if self.step < 1 else 0
        return round(x, digits)

    def describe(self):
        d = {**super().describe(), "min": self.lo, "max": self.hi, "step": self.step, "unit": self.unit}
        return {**d, "zero": self.zero} if self.zero else d


class Choice(Control):
    kind = "choice"

    def __init__(self, name, title, options, default):
        super().__init__(name, title, default)
        self.options = dict(options)

    def check(self, v):
        return isinstance(v, str) and v in self.options

    def describe(self):
        return {**super().describe(), "options": [[k, v] for k, v in self.options.items()]}


class Switch(Control):
    kind = "switch"

    def check(self, v):
        return isinstance(v, bool)


COLUMNS = 22                                          # grid width for pixel effects: about one column per key
BRIGHTNESS = Number("brightness", "Brightness", 0, 1, 1, 0.05, "%")


class Geometry:
    """Where the LEDs of one keyboard are, scaled to 0..1. LEDs without a place sit in the middle.
    leds: LED indices; pos: index -> (x, y) in key units; by_key: key name -> LED indices."""

    def __init__(self, leds, pos, by_key=None):
        self.leds, self.pos, self.by_key = list(leds), pos, by_key or {}
        p = {a: pos[a] for a in self.leds if a in pos}
        xs, ys = [x for x, _ in p.values()], [y for _, y in p.values()]
        x0, y0 = (min(xs), min(ys)) if p else (0, 0)
        w, h = (max(xs) - x0, max(ys) - y0) if p else (0, 0)
        self._place = {a: ((p[a][0] - x0) / w if w and a in p else 0.5, (p[a][1] - y0) / h if h and a in p else 0.5)
                       for a in self.leds}
        if len(p) < 2:
            self._place = dict.fromkeys(self.leds, (0.5, 0.5))
        ys = [round(self._place[a][1], 3) for a in p]
        rows = sorted({y for y in ys if ys.count(y) >= 2}) or sorted(set(ys)) or [0.5]
        # a row needs two or more LEDs; tall keys (number pad +, Enter) and lone keys join the nearest row, the upper on a tie
        self.rows = len(rows)
        self._cell = {}
        for a in self.leds:
            u, v = self._place[a]
            row = min(range(len(rows)), key=lambda i: (round(abs(rows[i] - round(v, 3)), 6), i))
            self._cell[a] = (min(COLUMNS - 1, int(u * COLUMNS)), row)
        # distance and angle in the keyboard's real aspect ratio, so circles are round
        ratio = h / w if w else 1.0
        rel = {a: (u - .5, (v - .5) * ratio) for a, (u, v) in self._place.items()}
        far = max((math.hypot(*d) for d in rel.values()), default=0) or 1.0
        self._distance = {a: math.hypot(*d) / far for a, d in rel.items()}
        self._angle = {a: math.atan2(dy, dx) / (2 * math.pi) % 1.0 for a, (dx, dy) in rel.items()}

    def place(self, a):
        return self._place.get(a, (0.5, 0.5))

    def cell(self, a):
        """(column 0..COLUMNS-1, row from the top)."""
        return self._cell.get(a, (COLUMNS // 2, self.rows // 2))

    def distance(self, a):
        """0 in the middle, 1 at the farthest LED."""
        return self._distance.get(a, 0.0)

    def angle(self, a):
        return self._angle.get(a, 0.0)

    def leds_of(self, key):
        return self.by_key.get(key, ())


class Pattern:
    """One effect. values holds all controls including brightness, already checked and completed with defaults."""
    name = title = group = ""
    controls = []
    needs = frozenset()                               # e.g. {"sound"}: the helper should capture sound

    def __init__(self, values, geo, rnd):
        self.values, self.geo, self.rnd = values, geo, rnd
        self.start, self.seen = None, 0               # first frame; last stroke seen
        self.over = {}                                # LED -> (color, strength): what a typing layer lays over others

    def frame(self, now, s):
        """LED -> (r, g, b) before brightness."""
        raise NotImplementedError

    def adopt(self, old):
        """Same effect with new settings: carry on with what it has collected so far."""
        self.start, self.seen = old.start, old.seen

    def new_strokes(self, s):
        """Strokes since the last call as [(key name, time)]; ones from before the first frame do not count."""
        strokes = getattr(s, "strokes", None) if s is not None else None
        if not strokes:
            return []
        new = [(k, t) for n, k, t in strokes if n > self.seen and (self.start is None or t >= self.start)]
        self.seen = max(self.seen, strokes[-1][0])
        return new

    def paint(self, now, s):
        if self.start is None:
            self.start = now
        self.over = {}
        h, f, black = self.values["brightness"], self.frame(now, s), (0, 0, 0)
        return {a: tuple(dim(x, h) for x in f.get(a, black)) for a in self.geo.leds}

    @classmethod
    def moving(cls, values):
        return True
