"""Group Motion: rainbow, visor, chaser, spin, fill."""
import colorsys
import math
import random

from .. import effects
from . import register
from .base import COLUMNS, Choice, Color, Number, Pattern, Switch
from .color import RAINBOW, ring

KEY = 1 / COLUMNS                                     # one key width, relative to the whole keyboard
BLACK = [0, 0, 0]


def hue(h):
    return tuple(x * 255 for x in colorsys.hsv_to_rgb(h, 1, 1))


class Rainbow(Pattern):
    name, title, group = "rainbow", "Rainbow", "Motion"
    controls = [Choice("shape", "Shape", {"horizontal": "Wave, left to right", "vertical": "Wave, top to bottom",
                                          "diagonal": "Wave, diagonal", "circle": "Circle", "spiral": "Spiral"}, "horizontal"),
                Switch("reverse", "Reverse", False),
                Number("speed", "Cycles per second", 0, 2, 0.3, 0.05, zero="still"),
                Number("count", "Rainbows at once", 0.5, 4, 1, 0.5)]

    def __init__(self, *a):
        super().__init__(*a)
        g, shape = self.geo, self.values["shape"]
        where = {"horizontal": lambda a: g.place(a)[0], "vertical": lambda a: g.place(a)[1],
                 "diagonal": lambda a: sum(g.place(a)) / 2, "circle": g.distance,
                 "spiral": lambda a: g.angle(a) + g.distance(a)}[shape]
        self.places = {a: where(a) * self.values["count"] for a in g.leds}

    def frame(self, now, s):
        run = now * self.values["speed"] * (1 if self.values["reverse"] else -1)
        return {a: hue((p + run) % 1.0) for a, p in self.places.items()}

    @classmethod
    def moving(cls, values):
        return values["speed"] > 0


class Visor(Pattern):
    name, title, group = "visor", "Visor", "Motion"
    controls = [Color("color", "Bar", [255, 0, 0]), Color("background", "Background", BLACK),
                Number("speed", "Sweeps per second", 0.1, 2, 0.5, 0.05), Number("width", "Width in keys", 1, 8, 3, 1)]

    def frame(self, now, s):
        v = self.values
        phase = now * v["speed"] % 1.0                # one sweep: there and back
        x = 2 * phase if phase < .5 else 2 - 2 * phase
        edge = v["width"] * KEY
        return {a: effects.mix(v["background"], v["color"], max(0.0, 1 - abs(self.geo.place(a)[0] - x) / edge))
                for a in self.geo.leds}


class Chaser(Pattern):
    name, title, group = "chaser", "Chaser", "Motion"
    controls = [Color("color", "Light", [0, 255, 120]), Color("background", "Background", BLACK),
                Number("speed", "Keys per second", 2, 40, 10, 1), Number("gap", "Gap in keys", 2, 12, 5, 1),
                Choice("path", "Path", {"rows": "Row by row", "around": "Round and round"}, "rows")]

    def __init__(self, *a):
        super().__init__(*a)
        g = self.geo
        if self.values["path"] == "around":
            self.slot = {a: i for i, a in enumerate(sorted(g.leds, key=g.angle))}
        else:                                         # place in its own row, from the left
            rows = {}
            for a in sorted(g.leds, key=lambda a: g.place(a)[0]):
                rows.setdefault(round(g.place(a)[1], 3), []).append(a)
            self.slot = {a: i for r in rows.values() for i, a in enumerate(r)}

    def frame(self, now, s):
        v = self.values
        x = now * v["speed"]
        return {a: effects.mix(v["background"], v["color"], max(0.0, 1 - (x - i) % v["gap"] / 2)) for a, i in self.slot.items()}


class Spin(Pattern):
    name, title, group = "spin", "Spin", "Motion"
    controls = [Color("colors", "Colors", RAINBOW, "wave"),
                Number("speed", "Turns per second", 0, 2, 0.25, 0.05, zero="still"), Number("arms", "Arms", 1, 6, 2, 1)]

    def frame(self, now, s):
        v, g = self.values, self.geo
        colors = ring(v["colors"])
        return {a: effects.ramp(colors, (g.angle(a) * v["arms"] - now * v["speed"]) % 1.0) for a in g.leds}

    @classmethod
    def moving(cls, values):
        return values["speed"] > 0 and isinstance(values["colors"], dict)


class Fill(Pattern):
    name, title, group = "fill", "Fill one by one", "Motion"
    controls = [Color("color", "Color", [255, 160, 0], "area"), Color("background", "Background", BLACK),
                Number("speed", "Keys per second", 2, 60, 15, 1),
                Choice("order", "Order", {"left": "Left to right", "random": "Random"}, "left")]

    def __init__(self, *a):
        super().__init__(*a)
        g = self.geo
        self.left = sorted(g.leds, key=lambda a: (g.place(a)[0], g.place(a)[1]))
        self.round, self.order, self.seed = None, self.left, self.rnd.random()
        self.colors = effects.paint(self.values["color"], g.leds, g.pos, 1.0)    # color or gradient per key

    def _order(self, rnd):
        if self.values["order"] == "left":
            return self.left
        if rnd != self.round:                         # shuffled anew each round, but repeatable
            self.round, self.order = rnd, list(self.left)
            random.Random(f"{self.seed}/{rnd}").shuffle(self.order)
        return self.order

    def frame(self, now, s):
        v, n = self.values, len(self.left)
        if not n:
            return {}
        k = now * v["speed"]
        rnd, k = divmod(k, 2 * n)
        order = self._order(int(rnd))
        full = math.floor(k) if k < n else n - math.floor(k - n)
        lo, hi = (0, full) if k < n else (n - full, n)
        return {a: effects._now(self.colors[a], now) if lo <= i < hi else v["background"] for i, a in enumerate(order)}


register(Rainbow, Visor, Chaser, Spin, Fill)
