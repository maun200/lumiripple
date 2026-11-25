"""Group Color: solid color or gradient, breathing, color cycle."""
import math

from .. import effects
from . import register
from .base import Color, Number, Pattern

RAINBOW = {"stops": [[255, 0, 0], [255, 176, 0], [0, 255, 0], [0, 255, 255], [0, 0, 255], [255, 0, 255]],
           "direction": "horizontal", "speed": 0}


def ring(p):
    """Colors of a paint, closed again with the first one; a single color: just that color."""
    stops = p["stops"] if isinstance(p, dict) else [p]
    return [*stops, stops[0]]


def stops(p):
    return p["stops"] if isinstance(p, dict) else [p, p]


class Solid(Pattern):
    name, title, group = "solid", "Color / gradient", "Color"
    controls = [Color("color", "Color", [0, 40, 60], "area")]

    def __init__(self, *a):
        super().__init__(*a)
        self.plan = effects.paint(self.values["color"], self.geo.leds, self.geo.pos, 1.0)

    def frame(self, now, s):
        return {a: effects._now(v, now) for a, v in self.plan.items()}

    @classmethod
    def moving(cls, values):
        c = values["color"]
        return isinstance(c, dict) and c["speed"] > 0


class Breathing(Solid):
    name, title = "breathing", "Breathing"
    controls = [Color("color", "Color", [0, 120, 255], "area"), Number("rate", "Breaths per minute", 4, 60, 15, 1),
                Number("depth", "Darkest point", 0, 0.9, 0.1, 0.05, "%")]

    def frame(self, now, s):
        d = self.values["depth"]
        k = d + (1 - d) * (0.5 - 0.5 * math.cos(2 * math.pi * now * self.values["rate"] / 60))
        return {a: effects.scale(c, k) for a, c in super().frame(now, s).items()}

    @classmethod
    def moving(cls, values):
        return True


class Cycle(Pattern):
    name, title, group = "cycle", "Color cycle", "Color"
    controls = [Color("colors", "Colors", RAINBOW, "wave"), Number("period", "Seconds per cycle", 2, 120, 20, 1)]

    def frame(self, now, s):
        c = effects.ramp(ring(self.values["colors"]), now / self.values["period"] % 1.0)
        return dict.fromkeys(self.geo.leds, c)

    @classmethod
    def moving(cls, values):
        return isinstance(values["colors"], dict)


register(Solid, Breathing, Cycle)
