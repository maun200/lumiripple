"""Profile settings: defaults and strict validation. Everything that arrives from outside goes through merge()."""
import copy
import math

from . import keys

METRICS = {"cpu": "CPU load", "gpu": "GPU load", "ram": "RAM", "vram": "GPU memory", "cpu_temp": "CPU temperature",
           "gpu_temp": "GPU temperature"}
DIRECTIONS = {"horizontal": "Left to right", "vertical": "Top to bottom", "diagonal": "Diagonal", "radial": "Centre outwards"}
MAX_STOPS, MAX_GRADIENT_SPEED, MAX_STATS, MAX_HIGHLIGHTS = 8, 2, 12, 24
MACRO_SPEED = (0.25, 4.0)

DEFAULTS = {
    "brightness": 1.0,
    "pattern": {"kind": "solid", "values": {}},      # the effect under everything, see patterns/
    "layers": {"heat": False, "trail": False},       # typing effects that also run over any effect
    "wave": {"on": True, "color": [0, 255, 255], "brightness": 1.0, "speed": 9.0, "width": 0.9, "fade": 1.4},
    "pressed": {"on": True, "color": [255, 255, 255], "brightness": 1.0, "release": 0.35, "over_displays": True},
    "press": {"on": False, "min_ms": 30},           # ignore touches shorter than this (lighting only)
    "extra": {"brightness": 1.0, "colors": {}},      # LEDs that are not regular keys: label -> paint
    "highlight": {"on": True, "brightness": 1.0, "items": []},
    "stats": {"on": True, "brightness": 1.0, "colors": [[0, 200, 0], [255, 180, 0], [255, 0, 0]],
              "items": [{"metric": m, "start": s, "count": 4} for m, s in (("cpu", "F1"), ("gpu", "F5"), ("ram", "F9"))]},
    "sound": {"on": True, "brightness": 1.0, "colors": [[0, 120, 255], [255, 0, 200]], "sensitivity": 1.0, "areas": ["numpad"]},
    "mic": {"on": False, "brightness": 1.0, "colors": [[0, 255, 80], [255, 220, 0]], "sensitivity": 1.5, "areas": ["letters"]},
}
LIMITS = {"release": (0, 3), "min_ms": (5, 200), "brightness": (0, 1), "speed": (0.5, 40), "width": (0.15, 5), "fade": (0.2, 5), "sensitivity": (0.1, 5)}


def is_color(v):
    return isinstance(v, list) and len(v) == 3 and all(type(x) is int and 0 <= x <= 255 for x in v)


def is_paint(v):
    """A solid color [r, g, b] or a gradient."""
    if not isinstance(v, dict):
        return is_color(v)
    return (set(v) == {"stops", "direction", "speed"} and isinstance(v["stops"], list) and 2 <= len(v["stops"]) <= MAX_STOPS
            and all(map(is_color, v["stops"])) and isinstance(v["direction"], str) and v["direction"] in DIRECTIONS
            and type(v["speed"]) in (int, float) and 0 <= v["speed"] <= MAX_GRADIENT_SPEED)


def _stat(a):
    return (isinstance(a, dict) and set(a) == {"metric", "start", "count"} and isinstance(a["metric"], str)
            and a["metric"] in METRICS and isinstance(a["start"], str) and a["start"] in keys.BY_NAME
            and type(a["count"]) is int and 1 <= a["count"] <= 24)


def _highlight(a):
    return (isinstance(a, dict) and set(a) == {"keys", "color", "wave"} and isinstance(a["keys"], list)
            and all(isinstance(k, str) and k in keys.BY_NAME for k in a["keys"]) and len(set(a["keys"])) == len(a["keys"])
            and all(a[k] is None or is_paint(a[k]) for k in ("color", "wave")))


def _check(path, key, old, new):
    if path == ("pattern",):
        from . import patterns                       # here, because patterns needs this module
        return patterns.merge(old, new)
    if key == "color":
        ok = is_paint(new)
    elif path[:1] == ("extra",) and key == "colors":
        ok = (isinstance(new, dict) and len(new) <= 64 and all(
            isinstance(k, str) and 1 <= len(k) <= 64 and k.isprintable() and is_paint(v) for k, v in new.items()))
    elif isinstance(old, dict):
        return merge(old, new, path)
    elif key == "items":
        check, top = (_stat, MAX_STATS) if path[0] == "stats" else (_highlight, MAX_HIGHLIGHTS)
        ok = isinstance(new, list) and len(new) <= top and all(map(check, new))
    elif key == "areas":
        ok = isinstance(new, list) and all(isinstance(a, str) and a in keys.AREAS for a in new) and len(set(new)) == len(new)
    elif isinstance(old, bool):
        ok = isinstance(new, bool)
    elif key == "colors":
        ok = isinstance(new, list) and len(new) == len(old) and all(map(is_color, new))
    else:
        lo, hi = LIMITS[key]
        ok = type(new) in (int, float) and math.isfinite(new) and lo <= new <= hi
    if not ok:
        raise ValueError(f"invalid value for {'.'.join(path)}")
    return copy.deepcopy(new)


def merge(old, new, path=()):
    """Return old with new laid over it. Raises ValueError and changes nothing if anything does not fit."""
    if not isinstance(new, dict):
        raise ValueError("settings must be an object")
    out = copy.deepcopy(old)
    for k, v in new.items():
        if k not in old:
            raise ValueError(f"unknown setting {'.'.join((*path, str(k)))}")
        out[k] = _check((*path, k), k, old[k], v)
    return out


def title(text):
    text = text.strip() if isinstance(text, str) else ""
    if not (1 <= len(text) <= 40 and text.isprintable()):
        raise ValueError("Please enter a name with 1 to 40 characters")
    return text
