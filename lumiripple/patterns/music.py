"""Group Music: whole-keyboard effects from the computer's sound (16 bands, stereo levels). They never use the microphone."""
import colorsys

from .. import effects
from . import register
from .base import COLUMNS, Color, Number, Pattern
from .color import stops

SENS = Number("sensitivity", "Sensitivity", 0.2, 5, 1, 0.1, "×")
MIDDLE = (COLUMNS - 1) / 2


class Music(Pattern):
    group, needs = "Music", frozenset({"sound"})

    def bands(self, s):
        return getattr(s, "sound", None) or [0.0] * 16


class Spectrum(Music):
    name, title = "spectrum", "Mirrored spectrum"
    controls = [Color("colors", "Colors", {"stops": [[0, 120, 255], [255, 0, 200]], "direction": "horizontal", "speed": 0},
                      "wave"), SENS]

    def frame(self, now, s):
        b, g, v = self.bands(s), self.geo, self.values
        colors, rows = stops(v["colors"]), g.rows
        out = {}
        for a in g.leds:
            c, r = g.cell(a)
            i = int(abs(c - MIDDLE))                  # 0 in the middle (bass) to 10 outside (treble)
            lo = i * 16 // 11                         # each column covers its bands, none is skipped
            level = max(b[lo:max((i + 1) * 16 // 11, lo + 1)])
            height = min(1.0, level * v["sensitivity"]) * rows
            k = rows - 1 - r                          # row from the bottom
            out[a] = effects.scale(effects.ramp(colors, k / max(rows - 1, 1)), min(max(height - k, 0.0), 1.0))
        return out


class Pulse(Music):
    name, title = "pulse", "Bass pulse"
    controls = [Color("color", "Color", [255, 0, 80], "area"), SENS, Number("depth", "Darkest point", 0, 0.9, 0.05, 0.05, "%")]

    def __init__(self, *a):
        super().__init__(*a)
        self.plan = effects.paint(self.values["color"], self.geo.leds, self.geo.pos, 1.0)

    def frame(self, now, s):
        b, v = self.bands(s), self.values
        k = v["depth"] + (1 - v["depth"]) * min(1.0, max(b[0], b[1]) * v["sensitivity"])
        return {a: effects.scale(effects._now(p, now), k) for a, p in self.plan.items()}


class BassWave(Music):
    name, title = "bass_wave", "Bass wave"
    controls = [Color("color", "Wave", [0, 200, 255]), Color("background", "Background", [0, 0, 0], "area"), SENS,
                Number("speed", "Wave speed", 0.2, 3, 1, 0.1)]
    LOCK, WIDTH, END, MOST = 0.15, 0.12, 1.3, 8

    def __init__(self, *a):
        super().__init__(*a)
        g = self.geo
        self.ground = effects.paint(self.values["background"], g.leds, g.pos, 1.0)
        self.rings, self.mean, self.before, self.beat = [], 0.0, 0.0, -1e9

    def frame(self, now, s):
        b, v = self.bands(s), self.values
        bass = (b[0] + b[1]) / 2
        # beat: the bands are already in dB, so a fixed step over the running mean (0.12 ≈ 6 dB, smaller with
        # more sensitivity), rising, and not right after the last one
        if bass - self.mean > 0.12 / v["sensitivity"] and bass > self.before and now - self.beat >= self.LOCK:
            self.beat = now
            self.rings = (self.rings + [now])[-self.MOST:]
        self.mean, self.before = self.mean * 0.9 + bass * 0.1, bass
        self.rings = [r for r in self.rings if 0 <= (now - r) * v["speed"] <= self.END]
        radii = [(now - r) * v["speed"] for r in self.rings]
        out = {}
        for a, g in self.ground.items():
            d = self.geo.distance(a)
            x = max((max(0.0, 1 - abs(d - r) / self.WIDTH) * (1 - r / self.END) for r in radii), default=0.0)
            out[a] = effects.mix(effects._now(g, now), v["color"], x)
        return out


class Stereo(Music):
    name, title = "stereo", "Left / right"
    controls = [Color("colors", "Colors", {"stops": [[0, 255, 0], [255, 255, 0], [255, 0, 0]], "direction": "horizontal",
                                           "speed": 0}, "wave"), SENS]

    def frame(self, now, s):
        v, g = self.values, self.geo
        st = getattr(s, "stereo", None)
        if st is None:                                # no stereo: the loudest band for both sides
            st = [max(self.bands(s))] * 2
        colors, half = stops(v["colors"]), COLUMNS // 2
        out = {}
        for a in g.leds:
            c = g.cell(a)[0]
            side, d = (0, half - 1 - c) if c < half else (1, c - half)    # d: columns from the middle outwards
            x = min(max(st[side] * v["sensitivity"] * half - d, 0.0), 1.0)
            out[a] = effects.scale(effects.ramp(colors, d / max(half - 1, 1)), x)
        return out


class Pitch(Music):
    name, title = "pitch", "Hue follows pitch"
    controls = [SENS, Number("rest", "Brightness when silent", 0, 0.5, 0.05, 0.05, "%")]

    def __init__(self, *a):
        super().__init__(*a)
        self.tone = 0.0

    def frame(self, now, s):
        b, v = self.bands(s), self.values
        total = sum(b)
        if total > 0:                                 # centre of the bands: low red, high violet; follows softly
            goal = sum(i * x for i, x in enumerate(b)) / total / 15 * 0.8
            self.tone += (goal - self.tone) * 0.15
        k = v["rest"] + (1 - v["rest"]) * min(1.0, max(b) * v["sensitivity"])
        return dict.fromkeys(self.geo.leds, effects.scale(tuple(x * 255 for x in colorsys.hsv_to_rgb(self.tone, 1, 1)), k))


register(Spectrum, Pulse, BassWave, Stereo, Pitch)
