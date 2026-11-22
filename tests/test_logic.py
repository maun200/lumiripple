import unittest

from lumiripple import config, effects, keys, macros, openrgb

BOARD = openrgb.demo_board()


def grad(*stops, direction="horizontal", speed=0):
    return {"stops": [list(s) for s in stops], "direction": direction, "speed": speed}


class Base(unittest.TestCase):
    def setUp(self):
        self.e = config.merge(config.DEFAULTS, {"base": {"color": [0, 0, 0]}, "stats": {"on": False}, "sound": {"on": False}})
        self.s, self.board = effects.State(), BOARD

    def frame(self, t=0.0):
        f = effects.render(self.board, self.e, self.s, t, effects.make_plan(self.e, self.board))
        return {n: f[i[0]] for n, i in [*self.board.by_key.items(), *self.board.extras.items()]}

    def wave(self, key, t=0.0):
        k = keys.BY_NAME[key]
        self.s.waves.append(((k.x + k.w / 2, k.y + k.h / 2), t, key))


class Keys(unittest.TestCase):
    def test_tables_only_know_existing_keys(self):
        names = set(keys.BY_NAME)
        self.assertEqual(len(names), len(keys.KEYS))
        self.assertLessEqual(set(keys.EVDEV.values()) - {f"F{i}" for i in range(13, 25)}, names)
        for table in (keys.MAC, keys.WIN_SCAN):
            self.assertLessEqual(set(table.values()), names)
        for _, want in keys.AREAS.values():
            self.assertLessEqual(want or set(), names)
        self.assertLessEqual(set(keys.ALIASES.values()), names)

    def test_keys_of_one_row_do_not_overlap_on_ansi(self):
        ks = [k for k in keys.KEYS if k.name not in ("Right Windows", "\\ (ISO)", "#")]
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                self.assertFalse(a.x < b.x + b.w - .01 and b.x < a.x + a.w - .01 and a.y < b.y + b.h - .01 and b.y < a.y + a.h - .01, (a, b))


class Boards(unittest.TestCase):
    def make(self, rows):
        flat = [n for r in rows for n in r]
        w = max(map(len, rows))
        m, i = [], 0
        for r in rows:
            m.append([i + x if x < len(r) else openrgb.NONE for x in range(w)])
            i += len(r)
        return openrgb.Board({"name": "t", "vendor": "", "serial": "", "description": "", "zones": [{"matrix": m, "leds": len(flat)}],
                              "leds": [n if n.startswith("!") else f"Key: {n}" for n in flat]})

    def test_qwertz_and_azerty_are_recognised_by_position(self):
        b = self.make([list("QWERTZUIOPÜ"), list("ASDFGHJKLÖÄ"), list("YXCVBNM")])
        self.assertEqual((b.leds[5], b.leds[22], b.leds[10], b.leds[20]), ("Y", "Z", "[", ";"))
        self.assertEqual(b.label("Z"), "Y")
        b = self.make([list("AZERTYUIOP"), list("QSDFGHJKLM"), list("WXCVBN,;")])
        self.assertEqual((b.leds[0], b.leds[1], b.leds[10], b.leds[19], b.leds[20]), ("Q", "W", "A", ";", "Z"))
        b = self.make([list("QWERTY"), list("ASDF"), list("ZXCV")])
        self.assertEqual((b.leds[5], b.leds[10]), ("Y", "Z"))

    def test_unknown_and_unnamed_lights_become_extras_with_a_place(self):
        b = self.make([["Q", "W", "!bar 1", "!bar 2"], ["Key9", "A"]])
        self.assertEqual(set(b.extras), {"!bar 1", "!bar 2", "Key9"})
        self.assertEqual(len(b.pos), 6)
        self.assertEqual(b.rows, [["Q", "W"], ["A"]])

    def test_board_without_matrix(self):
        self.assertEqual(BOARD.extras, {"Logo": [109]})
        self.assertNotIn(109, BOARD.pos)


class Settings(unittest.TestCase):
    def test_merge_keeps_the_rest_and_the_defaults(self):
        n = config.merge(config.DEFAULTS, {"wave": {"color": [255, 0, 0]}})
        self.assertEqual((n["wave"]["color"], n["wave"]["speed"]), ([255, 0, 0], 9.0))
        self.assertEqual(config.DEFAULTS["wave"]["color"], [0, 255, 255])

    def test_rejects_everything_invalid(self):
        g, h, s = grad((0, 0, 0), (1, 1, 1)), {"keys": ["A"], "color": None, "wave": None}, {"metric": "cpu", "start": "F1", "count": 4}
        bad = [[], {"nope": 1}, {"wave": 5}, {"wave": {"speed": "x"}}, {"wave": {"speed": -1}}, {"wave": {"speed": float("nan")}}, {"wave": {"on": 1}},
               {"base": {"color": [0, 0, 300]}}, {"base": {"color": [True, 0, 0]}}, {"base": {"color": {}}}, {"base": {"color": {**g, "speed": 9}}},
               {"base": {"color": {**g, "direction": []}}}, {"base": {"color": {**g, "stops": [[0, 0, 0]]}}}, {"base": {"color": {**g, "x": 1}}},
               {"stats": {"colors": [[0, 0, 0]]}}, {"stats": {"items": [{**s, "metric": "x"}]}}, {"stats": {"items": [{**s, "start": "nokey"}]}},
               {"stats": {"items": [{**s, "count": 0}]}}, {"stats": {"items": [s] * 13}}, {"highlight": {"items": [{**h, "keys": ["A", "A"]}]}},
               {"highlight": {"items": [{**h, "keys": [4]}]}}, {"highlight": {"items": [{**h, "color": "red"}]}}, {"highlight": {"items": [s]}},
               {"sound": {"areas": ["nope"]}}, {"sound": {"areas": ["all", "all"]}}, {"mic": {"areas": [[]]}}, {"extra": {"colors": {"": [0, 0, 0]}}},
               {"extra": {"colors": {"Logo": "red"}}}, {"extra": {"colors": {"a\nb": [0, 0, 0]}}}, {"press": {"min_ms": 0}}, {"pressed": {"release": 9}}]
        for b in bad:
            with self.assertRaises(ValueError, msg=repr(b)):
                config.merge(config.DEFAULTS, b)

    def test_accepts_gradients_and_back(self):
        g = grad((0, 0, 0), (1, 2, 3), speed=1.5)
        e = config.merge(config.DEFAULTS, {"base": {"color": g}, "extra": {"colors": {"Logo": g}}})
        self.assertEqual(e["base"]["color"], g)
        self.assertEqual(config.merge(e, {"base": {"color": [1, 2, 3]}, "extra": {"colors": {}}})["extra"]["colors"], {})


class Waves(Base):
    def arrival(self):
        return next(t / 1000 for t in range(4000) if self.frame(t / 1000)["L"][0] > 100)

    def test_width_never_changes_the_speed(self):
        self.e["wave"].update(color=[255, 255, 255], speed=8, fade=5)
        self.e["pressed"]["on"] = False
        self.wave("A")
        times = []
        for w in (.15, .5, 2, 5):
            self.e["wave"]["width"] = w
            times.append(self.arrival())
        self.assertLess(max(times) - min(times), .005, times)
        self.assertAlmostEqual(times[0], 1.0, delta=.06)

    def test_own_wave_color_and_blending(self):
        self.e["wave"]["color"] = [0, 0, 255]
        self.e["highlight"]["items"] = [{"keys": ["A"], "color": None, "wave": [255, 0, 0]}]
        self.wave("A")
        self.assertEqual(self.frame()["A"], (255, 0, 0))
        self.wave("A")
        self.s.waves[1] = (*self.s.waves[1][:2], "S")
        self.assertEqual(self.frame()["A"], (127, 0, 127))

    def test_gradient_over_time_and_end(self):
        self.e["wave"].update(color=grad((255, 0, 0), (0, 0, 255)), fade=1.0, speed=1, width=5)
        self.wave("A")
        a, b = self.frame(0)["A"], self.frame(.8)["A"]
        self.assertGreater(a[0], 200)
        self.assertGreater(b[2], b[0])
        self.assertEqual(self.frame(1.01)["A"], (0, 0, 0))
        self.assertFalse(effects.animated(self.s, self.e, 1.01))


class Displays(Base):
    def test_stats_bar_single_key_and_missing_value(self):
        self.e["stats"].update(on=True, items=[{"metric": "cpu", "start": "F1", "count": 4}, {"metric": "ram", "start": "1", "count": 1}])
        self.s.cpu, self.s.ram = .5, 1.0
        f = self.frame()
        self.assertEqual((f["F1"], f["F3"], f["1"]), ((0, 200, 0), (0, 0, 0), (255, 0, 0)))
        self.assertNotEqual(f["F2"], (0, 0, 0))
        self.s.cpu = self.s.ram = None
        self.assertEqual(self.frame()["F1"], (0, 0, 0))

    def test_sound_fills_the_number_pad_from_below(self):
        self.e["sound"]["on"] = True
        self.s.sound = [2 / 6] * 4 + [0] * 12
        lit = {k for k, c in self.frame().items() if c != (0, 0, 0)}
        self.assertEqual(lit, {"Number Pad 0", "Number Pad 1"})
        self.s.sound = [1.0] * 16
        self.assertLessEqual({"Media Stop", "Media Next", "Num Lock", "Number Pad Enter", "Number Pad +"}, {k for k, c in self.frame().items() if c != (0, 0, 0)})

    def test_microphone_on_letters(self):
        self.e["mic"].update(on=True, areas=["letters"], sensitivity=1.0)
        self.s.mic = [1.0] + [0] * 15
        lit = {k for k, c in self.frame().items() if c != (0, 0, 0)}
        self.assertTrue(lit and lit <= {"Q", "A", "Z"}, lit)

    def test_every_area_shows_something(self):
        for a in keys.AREAS:
            self.e["sound"].update(on=True, areas=[a])
            self.s.sound = [1.0] * 16
            self.assertTrue(any(c != (0, 0, 0) for c in self.frame().values()), a)

    def test_priority(self):
        self.e["stats"].update(on=True, items=[{"metric": "cpu", "start": "F1", "count": 1}])
        self.e["sound"].update(on=True, areas=["all"])
        self.e["highlight"]["items"] = [{"keys": ["F1", "W"], "color": [10, 20, 30], "wave": None}]
        self.s.cpu, self.s.sound = 1.0, [1.0] * 16
        self.wave("W")
        f = self.frame()
        self.assertEqual((f["F1"], f["W"]), ((255, 0, 0), (10, 20, 30)))
        self.s.pressed = {"W": (0.0, None), "F1": (0.0, None)}
        self.assertEqual(self.frame()["W"], (255, 255, 255))
        self.e["pressed"]["over_displays"] = False
        self.assertEqual((self.frame()["W"], self.frame()["F1"]), ((10, 20, 30), (255, 0, 0)))

    def test_pressed_key_fades(self):
        self.e["pressed"].update(color=[200, 100, 0], release=1.0)
        self.s.pressed = {"A": (0.0, 2.0)}
        self.assertEqual((self.frame(2.0)["A"], self.frame(2.5)["A"], self.frame(3.0)["A"]), ((200, 100, 0), (100, 50, 0), (0, 0, 0)))

    def test_extra_lights_and_recording(self):
        self.e["extra"]["colors"] = {"Logo": [1, 2, 3], "not on this board": [9, 9, 9]}
        self.assertEqual(self.frame()["Logo"], (1, 2, 3))
        self.s.recording = True
        self.assertEqual(self.frame(0.0)["Escape"], (255, 0, 0))

    def test_brightness(self):
        self.e["base"].update(color=[200, 100, 0], brightness=.5)
        self.e["brightness"] = .5
        self.assertEqual(self.frame()["A"], (50, 25, 0))


class Gradients(Base):
    def test_moving_gradient_is_seamless(self):
        self.e["base"]["color"] = grad((0, 0, 0), (200, 0, 0), speed=.5)
        self.assertTrue(effects.animated(self.s, self.e, 0))
        self.assertEqual(self.frame(0), self.frame(2.0))
        for i in range(200):
            self.assertLessEqual(abs(self.frame(i / 100)["A"][0] - self.frame((i + 1) / 100)["A"][0]), 3)

    def test_still_gradient_spans_the_board(self):
        self.e["base"]["color"] = grad((0, 0, 0), (200, 100, 50))
        self.assertFalse(effects.animated(self.s, self.e, 0))
        f = self.frame()
        self.assertEqual((f["Escape"], f["Media Next"]), ((0, 0, 0), (200, 100, 50)))

    def test_all_directions(self):
        for d in config.DIRECTIONS:
            self.e["base"]["color"] = grad((0, 0, 0), (255, 255, 255), direction=d)
            self.assertGreater(len(set(self.frame().values())), 3, d)


class Macros(unittest.TestCase):
    PLAN = [[0.0, "shift", True], [.1, "a", True], [.2, "a", False], [.3, "shift", False]]

    def player(self):
        out = []
        return macros.Player(lambda t, d: out.append((t, d))), out

    def test_recording_order_repeat_and_held_keys(self):
        r = macros.Recording(0.0)
        for t, k, d in ((.1, "x", False), (1.0, "a", True), (1.5, "a", True), (1.6, "b", True), (1.7, "b", False)):
            r.key(k, d, t)
        self.assertEqual([(k, d) for _, k, d in r.finish(2.0)], [("a", True), ("b", True), ("b", False), ("a", False)])
        self.assertEqual(r.finish(2.0)[0][0], 0)
        r.key("z", True, 61.0)
        self.assertTrue(r.expired(60.0))
        self.assertEqual(len(r.finish(61.0)), 4)

    def test_plays_in_time_and_releases_on_abort(self):
        p, out = self.player()
        p.start("m", self.PLAN, 100.0)
        p.tick(100.15)
        self.assertEqual(out, [("shift", True), ("a", True)])
        p.abort()
        self.assertEqual(sorted(out[2:]), [("a", False), ("shift", False)])
        self.assertIsNone(p.due(200))

    def test_speed_changes_while_playing(self):
        p, out = self.player()
        p.start("m", self.PLAN, 0.0, speed=2.0)
        p.tick(0.0)
        self.assertAlmostEqual(p.due(0.0), .05)
        p.tick(.051)
        p.set_speed(.5, .051)
        self.assertAlmostEqual(p.due(.051), .196)

    def test_instant_keeps_the_order(self):
        p, out = self.player()
        p.start("m", [[0, "s", True], [30, "a", True], [40, "a", False], [50, "s", False]], 0.0)
        p.tick(0.0)
        p.instant(1.0)
        for i in range(60):
            p.tick(1 + i * .002)
        self.assertEqual(out, [("s", True), ("a", True), ("a", False), ("s", False)])

    def test_view(self):
        p, _ = self.player()
        p.start("m", [[0.0, "s", True], [1.0, "a", True], [2.0, "a", False]], 0.0, speed=2.0)
        p.tick(0.0)
        v = p.view(.25, str.upper)
        self.assertEqual((v["last"], v["next"]), ("S", "A"))
        self.assertAlmostEqual(v["total"], 1.0)


if __name__ == "__main__":
    unittest.main()
