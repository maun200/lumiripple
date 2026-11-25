"""State and commands, without threads or hardware. Everything the interface can do is a command here."""
import copy
import json
import math
import os
import time

from . import config, effects, keys, macros, patterns

TRIGGERS = [k.name for k in keys.KEYS] + [f"F{i}" for i in range(13, 25)]


class Refused(Exception):
    """A message that may be shown to the user."""


class Core:
    def __init__(self, folder, backend):
        self.file, self.backend = os.path.join(folder, "lumiripple.json"), backend
        self.player = macros.Player(backend.send)
        self.state = effects.State()
        self.recording = self.draft = None
        self.waiting = {}                           # held keys whose minimum time is still running
        self.boards, self.dirty = [], False
        self.sound_at = dict.fromkeys(effects.SOURCES, -math.inf)
        self.gpu_at = self.helper_at = -math.inf
        self.status = {"openrgb": False, "input": False, "audio": None, "error": None}
        self.changes = 0                            # counts settings changes, so plans can be cached
        self._load()

    # ---- storage ---------------------------------------------------------
    @staticmethod
    def _profile(p):
        ms = {}
        for n, m in p["macros"].items():
            ms[config.title(n)] = {"trigger": str(m["trigger"]), "speed": float(m["speed"]), "instant": bool(m["instant"]),
                                   "events": [[float(t), k, bool(d)] for t, k, d in m["events"]]}
        return {"settings": Core._settings(p["settings"]), "macros": ms}

    @staticmethod
    def _settings(stored):
        """Strict for everything but the effect: that one is read leniently, so a changed effect never throws the file
        away. Profiles from 0.1 had a base color; it becomes the effect "solid"."""
        s = dict(stored)
        base, pattern = s.pop("base", None), s.pop("pattern", None)
        if pattern is None and isinstance(base, dict):
            pattern = {"kind": "solid", "values": {"solid": {k: v for k, v in base.items() if k in ("color", "brightness")}}}
        out = config.merge(config.DEFAULTS, s)
        out["pattern"] = patterns.clean(pattern)
        return out

    def _load(self):
        self.data = {"active": "Default", "profile_key": None, "profiles": {}}
        try:
            with open(self.file, encoding="utf-8") as f:
                d = json.load(f)
            profiles = {config.title(n): self._profile(p) for n, p in d["profiles"].items()}
            pk = d["profile_key"] if d.get("profile_key") in TRIGGERS else None
            if profiles:
                self.data = {"active": d["active"] if d["active"] in profiles else next(iter(profiles)), "profile_key": pk,
                             "profiles": profiles}
        except FileNotFoundError:
            pass
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            os.replace(self.file, f"{self.file}.broken-{int(time.time())}")
            print("settings file unreadable, moved aside:", type(e).__name__, flush=True)
        self.data["profiles"].setdefault(self.data["active"], {"settings": copy.deepcopy(config.DEFAULTS), "macros": {}})

    def save(self):
        tmp = self.file + ".new"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
        os.replace(tmp, self.file)
        self.dirty = False

    @property
    def active(self):
        return self.data["active"]

    @property
    def p(self):
        return self.data["profiles"][self.active]

    @property
    def e(self):
        return self.p["settings"]

    def _changed(self):
        self.changes += 1
        self.dirty = True

    # ---- input -----------------------------------------------------------
    def key(self, name, token, down, now):
        """One key event from the backend. name may be None for unknown keys."""
        if self.backend.sees_own_events and self.player.active:
            return
        if self.recording:
            self.recording.key(token, down, now)
        if down and not self.recording and name is not None:
            if name == self.data["profile_key"]:
                names = list(self.data["profiles"])
                self._switch(names[(names.index(self.active) + 1) % len(names)])
            for n, m in self.p["macros"].items():
                if m["trigger"] == name and not self.player.active and name not in self.state.pressed:
                    self.player.start(n, m["events"], now, m["speed"])
                    if m["instant"]:
                        self.player.instant(now)
        if name not in keys.BY_NAME:
            return
        held = name in self.state.pressed and self.state.pressed[name][1] is None
        if down and not held and name not in self.waiting:
            if self.e["press"]["on"]:
                self.waiting[name] = now
            else:
                self._counts(name, now)
        elif not down:
            t = self.waiting.pop(name, None)
            if t is not None and now - t >= self.e["press"]["min_ms"] / 1000:
                self._counts(name, now)
            self._release(name, now)

    def _counts(self, name, now):
        k = keys.BY_NAME[name]
        self.state.waves = self.state.waves[-11:] + [((k.x + k.w / 2, k.y + k.h / 2), now, name)]
        self.state.pressed[name] = (now, None)
        self.state.stroke_no += 1
        self.state.strokes.append((self.state.stroke_no, name, now))

    def _release(self, name, now):
        if name in self.state.pressed and self.state.pressed[name][1] is None:
            self.state.pressed[name] = (self.state.pressed[name][0], now)

    def release_all(self, now):
        """Keyboard gone: nothing may stay pressed."""
        self.waiting.clear()
        for n in list(self.state.pressed):
            self._release(n, now)

    def due(self, now):
        """Seconds until something has to happen, or None."""
        out = [self.player.due(now)] if self.player.active else []
        out += [t + self.e["press"]["min_ms"] / 1000 - now for t in self.waiting.values()]
        return max(min(out), 0) if out else None

    def tick(self, now):
        self.player.tick(now)
        for name, t in list(self.waiting.items()):
            if now - t >= self.e["press"]["min_ms"] / 1000:
                del self.waiting[name]
                self._counts(name, now)
        if self.recording and self.recording.expired(now):
            self._stop(now)
        s = self.state
        for q, f in effects.SOURCES.items():
            if now - self.sound_at[q] > 1:
                setattr(s, f, None)
                if q == "sound":
                    s.stereo = None
        if now - self.gpu_at > 5:
            s.gpu = s.gpu_temp = s.vram = None
        s.recording = self.recording is not None
        fade, rel = self.e["wave"]["fade"], self.e["pressed"]["release"]
        s.waves = [w for w in s.waves if now - w[1] < fade]
        s.pressed = {n: t for n, t in s.pressed.items() if t[1] is None or now - t[1] <= rel}
        while s.strokes and now - s.strokes[0][2] > 2:     # effects take strokes within a frame; nothing is kept longer
            s.strokes.popleft()

    def _stop(self, now):
        self.draft, self.recording = self.recording.finish(now) or None, None

    def _switch(self, name):
        self.recording = self.draft = None
        self.player.abort()
        self.data["active"] = name
        self._changed()

    # ---- commands --------------------------------------------------------
    def command(self, b):
        try:
            f = getattr(self, f"_c_{b['cmd']}", None) if isinstance(b, dict) and isinstance(b.get("cmd"), str) else None
            if f is None:
                raise Refused("unknown command")
            return {"ok": True, **(f(b) or {})}
        except (Refused, ValueError) as e:
            return {"ok": False, "error": str(e)}
        except (KeyError, TypeError):
            return {"ok": False, "error": "incomplete command"}

    def _c_get(self, b):
        now = time.monotonic()
        board = self.boards[0] if self.boards else None
        return {"active": self.active, "profiles": list(self.data["profiles"]), "profile_key": self.data["profile_key"],
                "settings": self.e, "recording": self.recording is not None,
                "draft": sum(d for _, _, d in self.draft) if self.draft else 0,
                "macros": [{"name": n, **{k: m[k] for k in ("trigger", "speed", "instant")}} for n, m in self.p["macros"].items()],
                "playing": self.player.view(now, self.backend.label), "boards": [x.name for x in self.boards],
                "extras": sorted(board.extras) if board else [], "present": sorted(board.by_key) if board else [],
                "status": {**self.status, "helper": self.helper_at > now - 10}}

    def _c_meta(self, b):
        """Things that never change while running."""
        return {"keys": [[k.name, k.x, k.y, k.w, k.h] for k in keys.KEYS], "rows": keys.rows(), "triggers": TRIGGERS,
                "areas": {a: t for a, (t, _) in keys.AREAS.items()}, "groups": keys.GROUPS, "metrics": config.METRICS,
                "directions": config.DIRECTIONS, "limits": config.LIMITS, "defaults": config.DEFAULTS,
                "macro_speed": config.MACRO_SPEED, "max_gradient_speed": config.MAX_GRADIENT_SPEED, "max_stops": config.MAX_STOPS,
                "patterns": patterns.catalog(), "pattern_groups": patterns.GROUPS, "layers": list(patterns.LAYERS)}

    def _c_needs(self, b):
        self.helper_at = time.monotonic()
        st = self.e["stats"]
        return {**{q: self.e[q]["on"] and bool(self.e[q]["areas"]) or q in patterns.ALL[self.e["pattern"]["kind"]].needs
                   for q in effects.SOURCES},
                "gpu": st["on"] and any(a["metric"] in ("gpu", "vram", "gpu_temp") for a in st["items"])}

    def _c_set(self, b):
        self.p["settings"] = config.merge(self.e, b["settings"])
        self._changed()

    def _c_audio(self, b):
        v, q = b["levels"], b["source"]
        if not (isinstance(q, str) and q in effects.SOURCES and isinstance(v, list) and len(v) == effects.BANDS
                and all(type(x) in (int, float) and 0 <= x <= 1 for x in v)):
            raise Refused("invalid sound levels")
        st = b.get("stereo")
        if st is not None and not (q == "sound" and isinstance(st, list) and len(st) == 2
                                   and all(type(x) in (int, float) and 0 <= x <= 1 for x in st)):
            raise Refused("invalid sound levels")
        if q == "sound":
            self.state.stereo = st
        setattr(self.state, effects.SOURCES[q], v)
        self.sound_at[q] = time.monotonic()

    def _c_gpu(self, b):
        load, temp, mem = b["load"], b["temp"], b["memory"]
        if not (all(type(x) in (int, float) and math.isfinite(x) for x in (load, temp, mem)) and 0 <= load <= 1 and 0 <= mem <= 1):
            raise Refused("invalid GPU values")
        s = self.state
        s.gpu, s.gpu_temp, s.vram, self.gpu_at = load, min(max((temp - 30) / 60, 0), 1), mem, time.monotonic()

    def _c_helper_status(self, b):
        if not (b["audio"] is None or isinstance(b["audio"], str) and len(b["audio"]) <= 200):
            raise Refused("invalid status")
        self.status["audio"] = b["audio"]

    def _c_profile_key(self, b):
        if b["key"] is not None and b["key"] not in TRIGGERS:
            raise Refused("this key cannot be used")
        self.data["profile_key"] = b["key"]
        self._changed()

    def _free(self, text, but=None):
        text = config.title(text)
        if text.lower() in (n.lower() for n in self.data["profiles"] if n != but):
            raise Refused("A profile with this name already exists")
        return text

    def _known(self, name):
        if not isinstance(name, str) or name not in self.data["profiles"]:
            raise Refused("There is no such profile")
        return name

    def _c_profile_new(self, b):
        name = self._free(b["name"])
        self.data["profiles"][name] = copy.deepcopy(self.p)
        self._switch(name)

    def _c_profile_switch(self, b):
        self._switch(self._known(b["name"]))

    def _c_profile_rename(self, b):
        old = self._known(b["name"])
        new = self._free(b["title"], old)
        self.data["profiles"] = {new if n == old else n: p for n, p in self.data["profiles"].items()}
        if self.active == old:
            self.data["active"] = new
        self._changed()

    def _c_profile_delete(self, b):
        if self._known(b["name"]) == self.active:
            raise Refused("The active profile cannot be deleted")
        del self.data["profiles"][b["name"]]
        self._changed()

    def _c_profile_reset(self, b):
        if type(b["everything"]) is not bool:
            raise Refused("everything must be true or false")
        if b["everything"]:
            self.player.abort()
            self.recording = self.draft = None
            self.p["macros"] = {}
        self.p["settings"] = copy.deepcopy(config.DEFAULTS)
        self._changed()

    def _c_record_start(self, b):
        if not self.status["input"]:
            raise Refused("Key input is not available, see the status line")
        self.draft, self.recording = None, macros.Recording(time.monotonic())

    def _c_record_stop(self, b):
        if self.recording:
            self._stop(time.monotonic())
        if not self.draft:
            raise Refused("No key was recorded")
        return {"count": sum(d for _, _, d in self.draft)}

    def _c_record_discard(self, b):
        self.recording = self.draft = None

    @staticmethod
    def _speed(v):
        if not (type(v) in (int, float) and config.MACRO_SPEED[0] <= v <= config.MACRO_SPEED[1]):
            raise Refused("speed must be between 0.25 and 4")
        return float(v)

    def _c_macro_save(self, b):
        name, ms = config.title(b["name"]), self.p["macros"]
        if not self.draft:
            raise Refused("There is no recording")
        if name in ms:
            raise Refused("A macro with this name already exists")
        if not isinstance(b["trigger"], str) or b["trigger"] not in TRIGGERS:
            raise Refused("This key cannot trigger a macro")
        if any(m["trigger"] == b["trigger"] for m in ms.values()) or b["trigger"] == self.data["profile_key"]:
            raise Refused("This key is already in use")
        if len(ms) >= 32:
            raise Refused("At most 32 macros per profile")
        ms[name] = {"trigger": b["trigger"], "speed": 1.0, "instant": False, "events": self.draft}
        self.draft = None
        self._changed()

    def _macro(self, name):
        if not isinstance(name, str) or name not in self.p["macros"]:
            raise Refused("There is no such macro")
        return self.p["macros"][name]

    def _c_macro_set(self, b):
        m, speed = self._macro(b["name"]), self._speed(b["speed"])
        if type(b["instant"]) is not bool:
            raise Refused("instant must be true or false")
        m.update(speed=speed, instant=b["instant"])
        self._changed()

    def _c_macro_delete(self, b):
        self._macro(b["name"])
        del self.p["macros"][b["name"]]
        self._changed()

    def _c_play_speed(self, b):
        self.player.set_speed(self._speed(b["speed"]), time.monotonic())

    def _c_play_instant(self, b):
        self.player.instant(time.monotonic())

    def _c_play_cancel(self, b):
        self.player.abort()
