"""Effects ("patterns"): registry, validation and creation. Every effect describes its own controls."""
import copy
import functools
import random

from .base import BRIGHTNESS, Geometry, Number, dim  # noqa: F401  (Geometry is used from outside)

ALL = {}                                              # name -> class, in display order
GROUPS = ["Color", "Motion", "Nature", "Typing", "Music"]
LAYERS = ("heat", "trail")                            # typing effects that can also run over any effect
DEFAULT = {"kind": "solid", "values": {}}


def register(*classes):
    for c in classes:
        ALL[c.name] = c


@functools.cache
def _controls(cls):
    """Controls of an effect; with two or more colors, each color gets its own brightness."""
    cs, out, auto = list(cls.controls), [], set()
    names = {c.name for c in cs}
    several = sum(c.kind == "color" for c in cs) >= 2
    for c in cs:
        out.append(c)
        if several and c.kind == "color" and f"{c.name}_brightness" not in names:
            out.append(Number(f"{c.name}_brightness", f"Brightness: {c.title}", 0, 1, 1, 0.05, "%"))
            auto.add(c.name)
    return [*out, BRIGHTNESS], frozenset(auto)


def controls(kind):
    return _controls(ALL[kind])[0]


def _scaled(p, h):
    if isinstance(p, dict):
        return {**p, "stops": [[dim(x, h) for x in c] for c in p["stops"]]}
    return [dim(x, h) for x in p]


def _snap(control, v):
    return control.snap(v) if control.kind == "number" else copy.deepcopy(v)


def defaults(kind):
    return {c.name: copy.deepcopy(c.default) for c in controls(kind)}


def values(setting, kind=None):
    """All values of an effect: the stored ones laid over the defaults."""
    kind = kind or setting["kind"]
    return {**defaults(kind), **copy.deepcopy(setting["values"].get(kind, {}))}


def merge(old, new):
    """Check a partial change (kind and/or values of single effects) and apply it. ValueError if anything is wrong."""
    if not isinstance(new, dict) or not set(new) <= {"kind", "values"}:
        raise ValueError("invalid value for pattern")
    out = copy.deepcopy(old)
    if "kind" in new:
        if not isinstance(new["kind"], str) or new["kind"] not in ALL:
            raise ValueError("unknown effect")
        out["kind"] = new["kind"]
    if "values" in new:
        if not isinstance(new["values"], dict):
            raise ValueError("invalid effect values")
        for kind, v in new["values"].items():
            if not isinstance(kind, str) or kind not in ALL or not isinstance(v, dict):
                raise ValueError("unknown effect")
            allowed = {c.name: c for c in controls(kind)}
            for k, x in v.items():
                if k not in allowed or not allowed[k].check(x):
                    raise ValueError(f"invalid value for pattern.{kind}.{k}")
            out["values"].setdefault(kind, {}).update({k: _snap(allowed[k], x) for k, x in v.items()})
    return out


def clean(setting):
    """Read stored settings leniently: unknown and invalid parts are dropped and defaults fill the gaps, so a changed
    or removed effect never throws the whole settings file away."""
    out = copy.deepcopy(DEFAULT)
    if not isinstance(setting, dict):
        return out
    if isinstance(setting.get("kind"), str) and setting["kind"] in ALL:
        out["kind"] = setting["kind"]
    vals = setting.get("values")
    for kind, v in (vals.items() if isinstance(vals, dict) else ()):
        if isinstance(kind, str) and kind in ALL and isinstance(v, dict):
            allowed = {c.name: c for c in controls(kind)}
            good = {k: _snap(allowed[k], x) for k, x in v.items() if k in allowed and allowed[k].check(x)}
            if good:
                out["values"][kind] = good
    return out


def catalog():
    order = sorted(ALL.items(), key=lambda e: GROUPS.index(e[1].group))     # by group, inside as registered
    return [{"name": c.name, "title": c.title, "group": c.group, "controls": [x.describe() for x in controls(n)]}
            for n, c in order]


def moving(setting):
    return ALL[setting["kind"]].moving(values(setting))


def create(setting, geo, rnd=None):
    """Build an effect; region brightnesses are already worked into the colors."""
    kind, v = setting["kind"], values(setting)
    for c in controls(kind):                          # also values that did not come through merge/clean
        if c.kind == "number":
            v[c.name] = c.snap(v[c.name])
    used = dict(v)
    for name in _controls(ALL[kind])[1]:
        if v[f"{name}_brightness"] != 1:
            used[name] = _scaled(v[name], v[f"{name}_brightness"])
    p = ALL[kind](used, geo, rnd or random.Random())
    p.raw = v                                         # to tell later whether the settings changed
    return p


from . import color, keystrokes, motion, music, nature  # noqa: E402,F401  (they register the effects)
