"""Group Nature: starry sky, flicker, rain, storm, watercolor, fire, matrix, game of life."""
import math

from .. import effects
from . import register
from .base import COLUMNS, Color, Number, Pattern, Switch
from .color import RAINBOW, ring

JUMP = 2.0                                            # bigger time jumps (idle): start fresh instead of catching up


class WithBackground(Pattern):
    """Background as color or gradient; the state starts fresh after time jumps."""
    group = "Nature"

    def __init__(self, *a):
        super().__init__(*a)
        g = self.geo
        self.ground = effects.paint(self.values["background"], g.leds, g.pos, 1.0) if "background" in self.values else {}
        self.last = None

    def background(self, now):
        return {a: effects._now(v, now) for a, v in self.ground.items()}

    def jumped(self, now):
        """True if the state has to start fresh (first call, jump, time running backwards)."""
        fresh = self.last is None or now < self.last or now - self.last > JUMP
        self.last = now
        return fresh

    def cells(self, levels, now):
        """Grid levels {(column, row): 0..1} laid onto the LEDs, over the background."""
        c, ground = self.values["color"], self.background(now)
        return {a: effects.mix(ground[a], c, min(1.0, levels.get(self.geo.cell(a), 0.0))) for a in self.geo.leds}


class Stars(WithBackground):
    name, title = "stars", "Starry sky"
    controls = [Color("color", "Stars", [255, 255, 220]), Color("background", "Sky", [0, 0, 20], "area"),
                Number("count", "Stars at once", 1, 40, 12, 1), Number("twinkle", "Twinkle time in seconds", 0.3, 5, 1.5, 0.1)]

    def __init__(self, *a):
        super().__init__(*a)
        self.stars = []                               # [LED, start]

    def frame(self, now, s):
        v, leds = self.values, self.geo.leds
        if not leds:
            return {}
        if self.jumped(now):                          # staggered, so they do not all twinkle at once
            self.stars = [[self.rnd.choice(leds), now - self.rnd.random() * v["twinkle"]] for _ in range(v["count"])]
        self.stars = [x for x in self.stars if now - x[1] < v["twinkle"]]
        while len(self.stars) < v["count"]:
            self.stars.append([self.rnd.choice(leds), now])
        out = self.background(now)
        for led, start in self.stars:
            out[led] = effects.mix(out[led], v["color"], max(math.sin(math.pi * (now - start) / v["twinkle"]), 0.0))
        return out


class Flicker(Pattern):
    name, title, group = "flicker", "Flicker", "Nature"
    controls = [Color("color", "Color", [255, 120, 0], "area"), Number("strength", "Strength", 0.05, 1, 0.4, 0.05, "%"),
                Number("speed", "Changes per second", 1, 20, 6, 1)]

    def __init__(self, *a):
        super().__init__(*a)
        self.plan = effects.paint(self.values["color"], self.geo.leds, self.geo.pos, 1.0)
        self.tick, self.noise = None, (None, None)

    def _fresh(self):
        return {a: self.rnd.random() for a in self.geo.leds}

    def frame(self, now, s):
        v = self.values
        k, rest = divmod(now * v["speed"], 1.0)
        if self.tick is None or not 0 <= k - self.tick <= 1:
            self.noise = (self._fresh(), self._fresh())
        elif k == self.tick + 1:
            self.noise = (self.noise[1], self._fresh())
        self.tick = k
        a0, a1 = self.noise
        return {a: effects.scale(effects._now(p, now), 1 - v["strength"] * (a0[a] + (a1[a] - a0[a]) * rest))
                for a, p in self.plan.items()}


class Rain(WithBackground):
    name, title = "rain", "Rain"
    controls = [Color("color", "Drops", [0, 120, 255]), Color("background", "Background", [0, 0, 0], "area"),
                Number("count", "Drops per second", 1, 40, 8, 1), Number("fall", "Fall time in seconds", 0.2, 3, 0.8, 0.1)]

    def __init__(self, *a):
        super().__init__(*a)
        self.drops, self.next = [], 0.0               # [column, start]

    def frame(self, now, s):
        v, rows = self.values, self.geo.rows
        if self.jumped(now):
            self.drops, self.next = [], now
        while self.next <= now:
            self.drops.append([self.rnd.randrange(COLUMNS), self.next])
            self.next += self.rnd.expovariate(v["count"])
        self.drops = [d for d in self.drops if (now - d[1]) / v["fall"] * rows < rows + 1]
        levels = {}
        for col, start in self.drops:
            head = (now - start) / v["fall"] * rows
            for row, x in ((int(head), 1.0), (int(head) - 1, 0.4)):
                if 0 <= row < rows:
                    levels[(col, row)] = max(levels.get((col, row), 0.0), x)
        return self.cells(levels, now)


class Storm(WithBackground):
    name, title = "storm", "Storm"
    controls = [Color("background", "Sky", [0, 0, 40], "area"), Color("color", "Lightning", [220, 220, 255]),
                Number("rate", "Flashes per minute", 1, 60, 10, 1)]
    SHAPE = ((0.08, 1.0), (0.14, 0.0), (0.26, 1.0))   # double flash: up to this time this strength

    def __init__(self, *a):
        super().__init__(*a)
        self.flash, self.next = None, 0.0

    def _strength(self, age):
        for until, x in self.SHAPE:
            if age < until:
                return x
        return max(0.0, 1 - (age - 0.26) / 0.4)

    def frame(self, now, s):
        v = self.values
        if self.jumped(now):
            self.flash, self.next = None, now + self.rnd.expovariate(v["rate"] / 60)
        if now >= self.next:
            self.flash, self.next = self.next, self.next + self.rnd.expovariate(v["rate"] / 60)
        x = self._strength(now - self.flash) if self.flash is not None else 0.0
        return {a: effects.mix(c, v["color"], x) for a, c in self.background(now).items()}


class Watercolor(Pattern):
    name, title, group = "watercolor", "Watercolor", "Nature"
    controls = [Color("colors", "Colors", RAINBOW, "wave"), Number("speed", "Speed", 0, 1, 0.1, 0.05, zero="still"),
                Number("size", "Size of the blots", 1, 5, 2, 0.5)]

    def frame(self, now, s):
        v, g = self.values, self.geo
        colors, k, t = ring(v["colors"]), 2 * math.pi * 1.5 / v["size"], now * v["speed"] * 2 * math.pi
        out = {}
        for a in g.leds:
            u, w = g.place(a)
            p = 0.5 + (math.sin(u * k + t) + math.sin(w * k * 1.3 - t * 1.3 + 1) + math.sin((u + w) * k * 0.7 + t * 0.7 + 2)) / 6
            out[a] = effects.ramp(colors, p % 1.0)
        return out

    @classmethod
    def moving(cls, values):
        return values["speed"] > 0 and isinstance(values["colors"], dict)


class Fire(WithBackground):
    name, title = "fire", "Fire"
    controls = [Color("colors", "Colors", {"stops": [[255, 0, 0], [255, 80, 0], [255, 224, 0]], "direction": "horizontal",
                                           "speed": 0}, "wave"),
                Number("height", "Height", 0.2, 1, 0.6, 0.05, "%"), Number("speed", "Speed", 0.2, 3, 1, 0.1)]
    STEPS = 20                                        # simulation steps per second at speed 1

    def frame(self, now, s):
        v, rows = self.values, self.geo.rows
        if self.jumped(now):
            self.heat = [[0.0] * rows for _ in range(COLUMNS)]
            self.t0, self.steps = now, 0
        want = int((now - self.t0) * self.STEPS * v["speed"])
        for _ in range(min(want - self.steps, 5)):
            self._step()
        self.steps = want
        colors, out = ring(v["colors"])[:-1], {}
        for a in self.geo.leds:
            c, r = self.geo.cell(a)
            h = min(1.0, self.heat[c][r])
            out[a] = effects.scale(effects.ramp(colors, h), min(1.0, h * 2))
        return out

    def _step(self):
        h, rows, r = self.heat, self.geo.rows, self.rnd
        cool = (1.25 - self.values["height"]) * 1.6 / max(rows, 1)
        for c in range(COLUMNS):
            for row in range(rows):
                h[c][row] = max(0.0, h[c][row] - r.random() * cool)
        for row in range(rows - 1):                   # heat rises: computed from below, slightly sideways
            for c in range(COLUMNS):
                below = h[c][row + 1]
                side = (h[(c - 1) % COLUMNS][row + 1] + h[(c + 1) % COLUMNS][row + 1]) / 2
                h[c][row] = (below * 2 + side) / 3.15
        for c in range(COLUMNS):                      # new embers at the bottom
            if r.random() < 0.5:
                h[c][rows - 1] = min(1.0, h[c][rows - 1] + 0.4 + r.random() * 0.6)


class Matrix(Pattern):
    name, title, group = "matrix", "Matrix", "Nature"
    controls = [Color("color", "Characters", [0, 255, 70]), Number("count", "Trails at once", 1, 20, 6, 1),
                Number("speed", "Keys per second", 2, 30, 8, 1)]
    TAIL = 4

    def __init__(self, *a):
        super().__init__(*a)
        self.trails, self.last = [], None             # [column, start]

    def frame(self, now, s):
        v, rows, r = self.values, self.geo.rows, self.rnd
        way = (rows + self.TAIL + 1) / v["speed"]
        if self.last is None or now < self.last or now - self.last > JUMP:
            self.trails = [[r.randrange(COLUMNS), now - r.random() * way] for _ in range(v["count"])]
        self.last = now
        self.trails = [t for t in self.trails if now - t[1] < way]
        while len(self.trails) < v["count"]:
            self.trails.append([r.randrange(COLUMNS), now + r.random() * 0.5])
        levels = {}
        for col, start in self.trails:
            head = int((now - start) * v["speed"])
            for d in range(self.TAIL + 1):
                if 0 <= head - d < rows:
                    levels[(col, head - d)] = max(levels.get((col, head - d), -1), d == 0 and 2 or 1 - d / (self.TAIL + 1))
        bright, black = effects.mix(v["color"], (255, 255, 255), 0.6), (0, 0, 0)
        out = {}
        for a in self.geo.leds:
            x = levels.get(self.geo.cell(a), 0)
            out[a] = bright if x == 2 else effects.scale(v["color"], x) if x > 0 else black
        return out


class Life(WithBackground):
    name, title = "life", "Game of Life"
    controls = [Color("color", "Cells", [0, 200, 255]), Color("background", "Background", [0, 0, 0]),
                Number("speed", "Generations per second", 1, 10, 3, 1), Switch("restart", "Start again when it stalls", True)]
    BLEND = 0.2

    def step(self, field):
        """One generation on the grid as a torus."""
        rows, count = self.geo.rows, {}
        for c, r in field:
            for dc in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    if dc or dr:
                        n = ((c + dc) % COLUMNS, (r + dr) % rows)
                        count[n] = count.get(n, 0) + 1
        return {n for n, k in count.items() if k == 3 or k == 2 and n in field}

    def _random(self):
        return {(c, r) for c in range(COLUMNS) for r in range(self.geo.rows) if self.rnd.random() < 0.35}

    def frame(self, now, s):
        v = self.values
        if self.jumped(now):
            self.field = self._random()
            self.before, self.history, self.next, self.born = set(), [], now + 1 / v["speed"], now
        if now >= self.next:                          # at most one generation per frame, no catching up
            new = self.step(self.field)
            if v["restart"] and (not new or new == self.field or new in self.history):
                new = self._random()
            self.history = (self.history + [self.field])[-6:]
            self.before, self.field = self.field, new
            self.born, self.next = now, now + 1 / v["speed"]
        x = min(1.0, (now - self.born) / self.BLEND)
        levels = {c: x for c in self.field - self.before}
        levels.update({c: 1.0 for c in self.field & self.before})
        levels.update({c: 1 - x for c in self.before - self.field})
        return self.cells(levels, now)


register(Stars, Flicker, Rain, Storm, Watercolor, Fire, Matrix, Life)
