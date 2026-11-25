"""Frame rendering. Pure functions, no hardware. Positions are in key units (one key = 1.0)."""
import math
from collections import deque
from dataclasses import dataclass, field

from . import keys

BANDS = 16
FRONT = 0.4                                          # soft edge ahead of a wave; fixed, so width never changes its speed
SOURCES = {"sound": "sound", "mic": "mic"}


@dataclass
class State:
    waves: list = field(default_factory=list)       # [((x, y), start time, key name)]
    cpu: float | None = None
    gpu: float | None = None
    ram: float | None = None
    vram: float | None = None
    cpu_temp: float | None = None
    gpu_temp: float | None = None
    sound: list | None = None                       # 16 levels 0..1, bass to treble
    mic: list | None = None
    pressed: dict = field(default_factory=dict)     # key name -> (since, released at or None)
    recording: bool = False
    stereo: list | None = None                      # computer sound left/right 0..1
    strokes: deque = field(default_factory=lambda: deque(maxlen=256))   # (number, key name, time), memory only
    stroke_no: int = 0


@dataclass
class Plan:
    """Everything that only depends on settings and keyboard, prepared once."""
    pattern: object                                 # the running effect (patterns.Pattern); keeps its state
    layers: list                                    # typing effects over it
    highlight: dict
    high_brightness: dict                           # LED -> brightness of its own color (for layers over highlights)
    wave_paint: dict
    stats: dict
    sound: dict


def mix(a, b, v):
    return tuple(x + (y - x) * v for x, y in zip(a, b))


def scale(c, h):
    return tuple(x * h for x in c)


def ramp(colors, t):
    t = min(max(t, 0), 1) * (len(colors) - 1)
    i = min(int(t), len(colors) - 2)
    return mix(colors[i], colors[i + 1], t - i)


def _places(direction, leds, pos):
    """LED -> place 0..1 inside the gradient, relative to the LEDs involved."""
    p = {a: pos[a] for a in leds if a in pos}
    out = dict.fromkeys(leds, 0.0)
    if not p:
        return out
    xs, ys = [x for x, _ in p.values()], [y for _, y in p.values()]
    x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    cx, cy = x0 + w / 2, y0 + h / 2
    far = max(math.hypot(x - cx, y - cy) for x, y in p.values())
    for a, (x, y) in p.items():
        u, v = (x - x0) / w if w else 0.0, (y - y0) / h if h else 0.0
        if direction == "radial":
            out[a] = math.hypot(x - cx, y - cy) / far if far else 0.0
        else:
            out[a] = {"horizontal": u, "vertical": v}.get(direction, (u + v) / 2)
    return out


def paint(p, leds, pos, brightness):
    """Spread a paint over LEDs: fixed colors, or (place, colors, speed) for moving gradients."""
    if not isinstance(p, dict):
        return dict.fromkeys(leds, scale(p, brightness))
    stops = [scale(c, brightness) for c in p["stops"]]
    places = _places(p["direction"], leds, pos)
    if not p["speed"]:
        return {a: ramp(stops, t) for a, t in places.items()}
    ring = (*stops, stops[0])                       # moving gradients close seamlessly
    return {a: (t, ring, p["speed"]) for a, t in places.items()}


def _now(v, now):
    if len(v) == 3 and isinstance(v[1], tuple):
        place, colors, speed = v
        return ramp(colors, (place - now * speed) % 1.0)
    return v


def wave_color(p, age):
    """age 0..1: a gradient runs from the start of the wave to its end."""
    return ramp(p["stops"], age) if isinstance(p, dict) else p


def _effect(setting, geo, old):
    """The effect for these settings; the old one stays if nothing changed, or hands over what it collected."""
    if old and old.name == setting["kind"] and old.raw == patterns.values(setting) and old.geo is geo:
        return old
    new = patterns.create(setting, geo)
    if old and old.name == new.name and old.geo.leds == geo.leds:
        new.adopt(old)                              # e.g. the heat map keeps its heat while you change a slider
    return new


def make_plan(e, board, old=None):
    """old: the previous plan for the same board; running effects carry on from it."""
    geo = old.pattern.geo if old and old.pattern.geo.pos is board.pos else patterns.Geometry(range(len(board.leds)), board.pos, board.by_key)
    pattern = _effect(e["pattern"], geo, old.pattern if old else None)
    layers = []
    for kind in (k for k in patterns.LAYERS if e["layers"][k] and k != e["pattern"]["kind"]):
        before = next((x for x in old.layers if x.name == kind), None) if old else None
        layers.append(_effect({"kind": kind, "values": e["pattern"]["values"]}, geo, before))
    hi, wave, bright = {}, {}, {}
    for label, p in e["extra"]["colors"].items():
        leds = board.extras.get(label, ())
        hi.update(paint(p, leds, board.pos, e["extra"]["brightness"]))
        bright.update(dict.fromkeys(leds, e["extra"]["brightness"]))
    for it in e["highlight"]["items"] if e["highlight"]["on"] else ():
        leds = [i for k in it["keys"] for i in board.by_key.get(k, ())]
        if it["color"]:
            hi.update(paint(it["color"], leds, board.pos, e["highlight"]["brightness"]))
            bright.update(dict.fromkeys(leds, e["highlight"]["brightness"]))
        if it["wave"]:
            wave.update(dict.fromkeys(it["keys"], it["wave"]))
    stats = {}
    for it in e["stats"]["items"] if e["stats"]["on"] else ():
        for row in board.rows:
            if it["start"] in row:
                i = row.index(it["start"])
                names = row[i:i + it["count"]]
                for n, k in enumerate(names):
                    stats.update(dict.fromkeys(board.by_key[k], (it["metric"], n, len(names))))
    return Plan(pattern, layers, hi, bright, wave, stats, _sound_plan(e, board))


def _sound_plan(e, board):
    """LED -> [(source, first band, last band + 1, row from below, rows)]."""
    out = {}
    for src in SOURCES:
        for name in e[src]["areas"] if e[src]["on"] else ():
            want = keys.AREAS[name][1]
            boxes = {}
            for i, led in enumerate(board.leds):
                if i in board.pos and (want is None or led in want):
                    k = keys.BY_NAME.get(led)
                    x, y = board.pos[i]
                    w, h = (k.w, k.h) if k else (1.0, 1.0)
                    boxes[i] = (x - w / 2, x + w / 2, y - h / 2, y + h / 2)
            if not boxes:
                continue
            x0, x1 = min(b[0] for b in boxes.values()), max(b[1] for b in boxes.values())
            lines = sorted({round(b[3], 2) for b in boxes.values()}, reverse=True)   # rows by lower edge, bottom first
            for i, (a, b, _, low) in boxes.items():
                first = min(int((a - x0) / (x1 - x0) * BANDS + 1e-6), BANDS - 1)
                last = max(int((b - x0) / (x1 - x0) * BANDS + 1e-6), first + 1)
                out.setdefault(i, []).append((src, first, last, lines.index(round(low, 2)), len(lines)))
    return out


def _moving(p):
    return isinstance(p, dict) and p["speed"] > 0


def animated(s, e, now):
    """Does the picture change by itself right now?"""
    return ((e["wave"]["on"] and any(now - w[1] < e["wave"]["fade"] for w in s.waves))
            or (e["pressed"]["on"] and any(r is not None and now - r < e["pressed"]["release"] for _, r in s.pressed.values()))
            or patterns.moving(e["pattern"]) or any(e["layers"].values())
            or any(map(_moving, e["extra"]["colors"].values())) or e["highlight"]["on"] and any(_moving(a["color"]) for a in e["highlight"]["items"])
            or any(e[q]["on"] and bool(b := getattr(s, f)) and max(b) > 0 for q, f in SOURCES.items()))


def _sound(fields, e, s):
    best, color = 0.0, None
    for src, a, b, row, rows in fields:
        lv = getattr(s, SOURCES[src])
        if lv:
            level = max(lv[a:b]) * e[src]["sensitivity"]
            v = min(max(level * rows - row, 0), 1)
            if v > best:
                t = row / (rows - 1) if rows > 1 else min(level, 1)
                best, color = v, scale(ramp(e[src]["colors"], t), e[src]["brightness"])
    return best, color


_failed = set()


def _safe(p, now, s):
    """An effect that fails must not take the lighting down: its keys stay dark, the error is told once."""
    try:
        return p.paint(now, s)
    except Exception as err:                         # any effect, any bug
        if p.name not in _failed:
            _failed.add(p.name)
            print(f"effect {p.name} failed: {type(err).__name__}: {err}", flush=True)
        p.over = {}
        return {}


def render(board, e, s, now, plan):
    """One frame: list of (r, g, b). Priority: pressed key (if over displays), stats, highlighted keys and other lights,
    sound, wave, typing layers, effect."""
    w = e["wave"]
    waves = [(p, now - t, scale(wave_color(plan.wave_paint.get(k, w["color"]), (now - t) / w["fade"]), w["brightness"]))
             for p, t, k in s.waves if 0 <= now - t < w["fade"]] if w["on"] else []
    g, down = e["pressed"], {}
    for name, (_, up) in s.pressed.items() if g["on"] else ():
        t = 0.0 if up is None else (now - up) / g["release"] if g["release"] else 1.0
        if t < 1:
            down.update(dict.fromkeys(board.by_key.get(name, ()), (scale(wave_color(g["color"], t), g["brightness"]), 1 - t)))
    out, base = [], _safe(plan.pattern, now, s)
    for layer in plan.layers:
        _safe(layer, now, s)
    over = [p for p in (plan.pattern, *plan.layers) if p.values.get("over_highlights")]
    for i in range(len(board.leds)):
        c, own = base.get(i, (0, 0, 0)), 0.0        # own: how strongly the key shows something itself
        for layer in plan.layers:                   # heat map / trail over the effect
            if i in layer.over:
                col, v = layer.over[i]
                c = mix(c, scale(col, layer.values["brightness"]), v)
        if i in plan.highlight:
            c, own = _now(plan.highlight[i], now), 1.0
            for p in over:                          # on request also over WASD & co., at their brightness
                if i in p.over:
                    col, v = p.over[i]
                    c = mix(c, scale(col, plan.high_brightness.get(i, 1.0)), v)
        value = getattr(s, plan.stats[i][0]) if i in plan.stats else None
        if value is not None:                       # a single key shows the value as a color
            _, step, count = plan.stats[i]
            v = min(max(value * count - step, 0), 1) if count > 1 else 1.0
            c = mix(c, scale(ramp(e["stats"]["colors"], step / (count - 1) if count > 1 else value), e["stats"]["brightness"]), v)
            own = max(own, v)
        elif i in plan.sound and i not in plan.highlight and i not in plan.stats:
            own, col = _sound(plan.sound[i], e, s)
            if col:
                c = mix(c, col, own)
        if waves and own < 1 and i in board.pos:
            x, y = board.pos[i]
            total = red = green = blue = 0.0
            for (px, py), age, col in waves:
                d = math.hypot(x - px, y - py) - w["speed"] * age
                v = math.exp(-(d / (FRONT if d > 0 else w["width"])) ** 2) * (1 - age / w["fade"])
                total, red, green, blue = total + v, red + col[0] * v, green + col[1] * v, blue + col[2] * v
            if total > 1e-4:                        # waves of different colors blend; displays keep priority
                c = mix(c, (red / total, green / total, blue / total), min(total, 1) * (1 - own))
        if i in down:                               # the pressed key itself
            col, v = down[i]
            c = mix(c, col, v if g["over_displays"] else v * (1 - own))
        if s.recording and board.leds[i] == "Escape":   # recording must be visible
            c = (255, 0, 0) if int(now * 4) % 2 == 0 else (0, 0, 0)
        out.append(tuple(min(max(int(dim(x, e["brightness"]) + 1e-6), 0), 255) for x in c))
    return out


from . import patterns  # noqa: E402  (at the end: patterns needs this module)
from .patterns.base import dim  # noqa: E402
