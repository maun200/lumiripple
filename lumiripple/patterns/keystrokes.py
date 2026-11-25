"""Group Typing: heat map and trail. Strokes live in memory only and are never stored."""
from .. import effects
from . import register
from .base import Color, Number, Pattern, Switch
from .color import ring

OVER = Switch("over_highlights", "Also over highlighted keys", False)


class Heat(Pattern):
    """Each key on its own: "full" strokes are fully hot, after "cool" minutes half of it is left."""
    name, title, group = "heat", "Heat map", "Typing"
    controls = [Color("colors", "Colors", {"stops": [[0, 0, 80], [0, 200, 255], [0, 255, 0], [255, 220, 0], [255, 0, 0]],
                                           "direction": "horizontal", "speed": 0}, "wave"),
                Number("full", "Strokes until fully hot", 10, 500, 100, 10),
                Number("cool", "Half cooled after minutes", 1, 30, 5, 1),
                Color("background", "Background", [0, 0, 80], "area"),
                Number("background_brightness", "Brightness: Background", 0, 1, 1, 0.05, "%"), OVER]

    def __init__(self, *a):
        super().__init__(*a)
        g = self.geo
        self.count, self.last = {}, None
        self.ground = effects.paint(self.values["background"], g.leds, g.pos, self.values["background_brightness"])

    def adopt(self, old):
        super().adopt(old)
        self.count, self.last = dict(old.count), old.last

    def frame(self, now, s):
        v = self.values
        if self.last is not None and now > self.last:  # half-life "cool" minutes
            k = 0.5 ** ((now - self.last) / (v["cool"] * 60))
            self.count = {a: n * k for a, n in self.count.items() if n * k > 1e-3}
        self.last = now
        for key, _ in self.new_strokes(s):
            for led in self.geo.leds_of(key):
                self.count[led] = min(self.count.get(led, 0.0) + 1, v["full"])
        colors, out = ring(v["colors"])[:-1], {}
        for a in self.geo.leds:
            ground, x = effects._now(self.ground[a], now), self.count.get(a, 0.0) / v["full"]
            if x > 0:                                 # cold keys show the background; the heat blends in over it
                hot = effects.ramp(colors, x)
                out[a] = effects.mix(ground, hot, min(1.0, x * 5))
                self.over[a] = (hot, min(1.0, x * 5))
            else:
                out[a] = ground
        return out


class Trail(Pattern):
    name, title, group = "trail", "Trail", "Typing"
    controls = [Color("color", "Trail", [255, 0, 180], "area"), Color("background", "Background", [0, 0, 0], "area"),
                Number("fade", "Fade time in seconds", 0.5, 20, 4, 0.5), OVER]

    def __init__(self, *a):
        super().__init__(*a)
        g = self.geo
        self.trail = effects.paint(self.values["color"], g.leds, g.pos, 1.0)
        self.ground = effects.paint(self.values["background"], g.leds, g.pos, 1.0)
        self.hit = {}                                 # LED -> time of the last stroke

    def adopt(self, old):
        super().adopt(old)
        self.hit = dict(old.hit)

    def frame(self, now, s):
        fade = self.values["fade"]
        for key, t in self.new_strokes(s):
            for led in self.geo.leds_of(key):
                if led in self.trail:
                    self.hit[led] = t
        self.hit = {a: t for a, t in self.hit.items() if 0 <= now - t < fade}
        out = {}
        for a, g in self.ground.items():
            g = effects._now(g, now)
            if a in self.hit:
                c, x = effects._now(self.trail[a], now), 1 - (now - self.hit[a]) / fade
                out[a] = effects.mix(g, c, x)
                self.over[a] = (c, x)
            else:
                out[a] = g
        return out


register(Heat, Trail)
