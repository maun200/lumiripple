import itertools
import json
import os
import random
import tempfile
import unittest

from lumiripple import config, core, effects, keys, openrgb, patterns
from lumiripple.patterns.base import Geometry, dim

try:
    from .test_core import Backend                   # python -m unittest (from the project folder, as CI does)
except ImportError:
    from test_core import Backend                    # python -m unittest discover -s tests

BOARD = openrgb.demo_board()
GEO = Geometry(range(len(BOARD.leds)), BOARD.pos, BOARD.by_key)


def variants(kind):
    """Defaults, plus every choice and switch value and the ends of every number."""
    out = [{}]
    for c in patterns.controls(kind):
        if c.kind == "choice":
            out += [{c.name: o} for o in c.options]
        elif c.kind == "switch":
            out.append({c.name: not c.default})
        elif c.kind == "number":
            out += [{c.name: c.lo}, {c.name: c.hi}]
    return out


def make(kind, values=None, seed=7):
    return patterns.create({"kind": kind, "values": {kind: values or {}}}, GEO, random.Random(seed))


def press(s, key, t):
    s.stroke_no += 1
    s.strokes.append((s.stroke_no, key, t))


class Catalog(unittest.TestCase):
    def test_groups_and_names(self):
        cat = patterns.catalog()
        self.assertEqual(len(cat), 23)
        self.assertEqual([c["group"] for c in cat], sorted((c["group"] for c in cat), key=patterns.GROUPS.index))
        self.assertTrue(all(c["controls"][-1]["name"] == "brightness" for c in cat))
        json.dumps(cat)                               # goes to the web page as it is

    def test_defaults_pass_their_own_check(self):
        for kind in patterns.ALL:
            for c in patterns.controls(kind):
                self.assertTrue(c.check(c.default), (kind, c.name))

    def test_two_colors_get_their_own_brightness(self):
        names = [c.name for c in patterns.controls("visor")]
        self.assertIn("color_brightness", names)
        self.assertIn("background_brightness", names)
        self.assertNotIn("color_brightness", [c.name for c in patterns.controls("solid")])
        self.assertEqual([c.name for c in patterns.controls("heat")].count("background_brightness"), 1)


class Validation(unittest.TestCase):
    def test_merge_checks_everything(self):
        p = patterns.DEFAULT
        self.assertEqual(patterns.merge(p, {"kind": "rain"})["kind"], "rain")
        self.assertEqual(patterns.merge(p, {"values": {"rain": {"count": 20}}})["values"]["rain"], {"count": 20})
        for bad in ({"kind": "nope"}, {"kind": 5}, {"x": 1}, {"values": {"rain": {"count": 999}}}, {"values": {"rain": {"x": 1}}},
                    {"values": {"nope": {}}}, {"values": {"rain": []}}, {"values": {"visor": {"color": {"stops": [[1, 2, 3]] * 2,
                    "direction": "horizontal", "speed": 0}}}}, {"values": {"rainbow": {"shape": "square"}}}, "x"):
            with self.assertRaises(ValueError, msg=bad):
                patterns.merge(p, bad)

    def test_settings_go_through_the_same_check(self):
        e = config.merge(config.DEFAULTS, {"pattern": {"kind": "fire", "values": {"fire": {"height": 0.3}}}})
        self.assertEqual(e["pattern"]["kind"], "fire")
        with self.assertRaises(ValueError):
            config.merge(config.DEFAULTS, {"pattern": {"kind": "nope"}})
        with self.assertRaises(ValueError):
            config.merge(config.DEFAULTS, {"layers": {"heat": 1}})

    def test_clean_keeps_what_is_good(self):
        c = patterns.clean({"kind": "gone", "values": {"rain": {"count": 20, "x": 1, "fall": 99}, "gone": {"a": 1}}})
        self.assertEqual(c, {"kind": "solid", "values": {"rain": {"count": 20}}})
        for junk in (None, 5, [], {"values": 3}):
            self.assertEqual(patterns.clean(junk), patterns.DEFAULT)


class EveryEffect(unittest.TestCase):
    def test_all_values_paint_every_led(self):
        for kind in patterns.ALL:
            for v in variants(kind):
                p = make(kind, v)
                s = effects.State(sound=[0.6] * 16, stereo=[0.8, 0.2])
                press(s, "A", 0.5)
                for t in (0.0, 0.5, 1.0, 3.3, 9.0):
                    f = p.paint(t, s)
                    self.assertEqual(set(f), set(GEO.leds), (kind, v))
                    self.assertTrue(all(len(c) == 3 and all(0 <= x <= 255 for x in c) for c in f.values()), (kind, v, t))

    def test_brightness_zero_is_black(self):
        for kind in patterns.ALL:
            f = make(kind, {"brightness": 0}).paint(3.3, effects.State(sound=[1] * 16))
            self.assertTrue(all(c == (0, 0, 0) for c in f.values()), kind)

    def test_empty_keyboard(self):
        for kind in patterns.ALL:
            p = patterns.create({"kind": kind, "values": {}}, Geometry([], {}), random.Random(1))
            self.assertEqual(p.paint(1.5, None), {}, kind)

    def test_still_effects_do_not_move(self):
        for kind, v in (("rainbow", {"speed": 0}), ("spin", {"speed": 0}), ("watercolor", {"speed": 0}), ("solid", {})):
            self.assertFalse(patterns.moving({"kind": kind, "values": {kind: v}}), kind)
            p = make(kind, v)
            self.assertEqual(p.paint(1.0, None), p.paint(7.0, None), kind)
        self.assertTrue(patterns.moving({"kind": "stars", "values": {}}))

    def test_rain_falls(self):
        p, s = make("rain", {"count": 40, "color": [0, 0, 255], "background": [0, 0, 0]}), None
        lit = [sum(1 for c in p.paint(t / 20, s).values() if c != (0, 0, 0)) for t in range(40)]
        self.assertGreater(max(lit), 0)


class Brightness(unittest.TestCase):
    def test_region_brightness_scales_one_color(self):
        f = make("visor", {"color": [200, 0, 0], "background": [0, 0, 200], "background_brightness": 0.5,
                           "speed": 0.1, "width": 1}).paint(0.0, None)
        self.assertIn((0, 0, 100), set(f.values()))

    def test_dim_keeps_one(self):
        self.assertEqual(dim(1, 0.3), 1.0)
        self.assertEqual(dim(200, 0.5), 100)
        self.assertEqual(dim(0.4, 0.5), 0.2)
        self.assertEqual(dim(5, 0), 0)
        f = make("solid", {"color": [1, 0, 0], "brightness": 0.2}).paint(0, None)
        self.assertEqual(set(f.values()), {(1, 0, 0)})

    def test_overall_brightness_keeps_one(self):
        e = config.merge(config.DEFAULTS, {"brightness": 0.3, "pattern": {"values": {"solid": {"color": [1, 0, 200]}}},
                                           "stats": {"on": False}, "sound": {"on": False}})
        f = effects.render(BOARD, e, effects.State(), 0, effects.make_plan(e, BOARD))
        self.assertEqual(f[BOARD.by_key["A"][0]], (1, 0, 60))


class Typing(unittest.TestCase):
    def test_heat_counts_and_cools(self):
        p, s = make("heat", {"full": 10, "cool": 1, "background": [0, 0, 0]}), effects.State()
        p.paint(0, s)
        for i in range(10):
            press(s, "A", 0.1 + i / 100)
        a = BOARD.by_key["A"][0]
        hot = p.paint(0.5, s)[a]
        self.assertEqual(p.count[a], 10)
        p.paint(60.5, s)
        self.assertAlmostEqual(p.count[a], 5, delta=0.1)              # half after one minute
        self.assertNotEqual(hot, (0, 0, 0))

    def test_old_strokes_do_not_count(self):
        s = effects.State()
        press(s, "A", 0.1)
        p = make("heat")
        p.paint(1.0, s)
        self.assertEqual(p.count, {})

    def test_trail_fades(self):
        p, s = make("trail", {"fade": 1, "color": [255, 0, 0], "background": [0, 0, 0]}), effects.State()
        p.paint(0, s)
        press(s, "S", 0.1)
        a = BOARD.by_key["S"][0]
        self.assertGreater(p.paint(0.2, s)[a][0], 200)
        self.assertEqual(p.paint(1.2, s)[a], (0, 0, 0))

    def test_adopt_keeps_the_heat(self):
        p, s = make("heat"), effects.State()
        p.paint(0, s)
        press(s, "A", 0.1)
        p.paint(0.2, s)
        q = make("heat", {"full": 20})
        q.adopt(p)
        self.assertEqual(q.count, p.count)


class Layers(unittest.TestCase):
    def setUp(self):
        self.e = config.merge(config.DEFAULTS, {"stats": {"on": False}, "sound": {"on": False}, "wave": {"on": False},
                                                "pressed": {"on": False}, "layers": {"trail": True},
                                                "pattern": {"kind": "rainbow", "values": {"trail": {"color": [255, 0, 0], "fade": 5}}},
                                                "highlight": {"items": [{"keys": ["W"], "color": [0, 0, 255], "wave": None}]}})
        self.s = effects.State()

    def run_(self, t0=0.0):
        plan = None
        for t in (t0, t0 + 0.2):
            plan = effects.make_plan(self.e, BOARD, plan)
            f = effects.render(BOARD, self.e, self.s, t, plan)
            if t == t0:
                press(self.s, "A", t0 + 0.1)
                press(self.s, "W", t0 + 0.1)
        return f

    def test_trail_over_any_effect(self):
        f = self.run_()
        self.assertGreater(f[BOARD.by_key["A"][0]][0], 200)
        self.assertEqual(f[BOARD.by_key["W"][0]], (0, 0, 255))      # highlighted keys stay as they are by default

    def test_over_highlights_on_request(self):
        self.e = config.merge(self.e, {"pattern": {"values": {"trail": {"over_highlights": True}}}})
        self.assertGreater(self.run_()[BOARD.by_key["W"][0]][0], 150)

    def test_layer_equal_to_the_effect_is_not_doubled(self):
        self.e = config.merge(self.e, {"pattern": {"kind": "trail"}})
        self.assertEqual(effects.make_plan(self.e, BOARD).layers, [])

    def test_plan_keeps_the_running_effect(self):
        p1 = effects.make_plan(self.e, BOARD)
        p2 = effects.make_plan(config.merge(self.e, {"wave": {"speed": 3.0}}), BOARD, p1)
        self.assertIs(p2.pattern, p1.pattern)
        self.assertIs(p2.layers[0], p1.layers[0])


class Service(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_old_base_color_becomes_solid(self):
        old = {"active": "Default", "profile_key": None, "profiles": {"Default": {"macros": {}, "settings": {
            "base": {"color": [9, 8, 7], "brightness": 0.5}, "wave": {"speed": 3.0}}}}}
        with open(os.path.join(self.dir, "lumiripple.json"), "w") as f:
            json.dump(old, f)
        c = core.Core(self.dir, Backend())
        self.assertEqual(c.e["pattern"], {"kind": "solid", "values": {"solid": {"color": [9, 8, 7], "brightness": 0.5}}})
        self.assertEqual(c.e["wave"]["speed"], 3.0)
        self.assertNotIn("base", c.e)

    def test_broken_effect_keeps_the_file(self):
        bad = {"active": "Default", "profile_key": None, "profiles": {"Default": {"macros": {}, "settings": {
            "pattern": {"kind": "gone", "values": {"rain": {"count": 999}}}, "wave": {"speed": 3.0}}}}}
        with open(os.path.join(self.dir, "lumiripple.json"), "w") as f:
            json.dump(bad, f)
        c = core.Core(self.dir, Backend())
        self.assertEqual(c.e["pattern"], patterns.DEFAULT)
        self.assertEqual(c.e["wave"]["speed"], 3.0)

    def test_strokes_are_counted_and_forgotten(self):
        c = core.Core(self.dir, Backend())
        c.status["input"] = True
        c.key("A", "a", True, 1.0)
        c.key("A", "a", False, 1.1)
        self.assertEqual([k for _, k, _ in c.state.strokes], ["A"])
        c.tick(3.5)
        self.assertEqual(len(c.state.strokes), 0)

    def test_music_effect_needs_sound(self):
        c = core.Core(self.dir, Backend())
        c.command({"cmd": "set", "settings": {"sound": {"on": False}}})
        self.assertFalse(c.command({"cmd": "needs"})["sound"])
        c.command({"cmd": "set", "settings": {"pattern": {"kind": "spectrum"}}})
        self.assertTrue(c.command({"cmd": "needs"})["sound"])

    def test_stereo_from_the_helper(self):
        c = core.Core(self.dir, Backend())
        self.assertTrue(c.command({"cmd": "audio", "source": "sound", "levels": [0.1] * 16, "stereo": [0.2, 0.9]})["ok"])
        self.assertEqual(c.state.stereo, [0.2, 0.9])
        for bad in ([1, 2], [0.1], "x", [0.5, -1]):
            self.assertFalse(c.command({"cmd": "audio", "source": "sound", "levels": [0.1] * 16, "stereo": bad})["ok"], bad)
        self.assertFalse(c.command({"cmd": "audio", "source": "mic", "levels": [0.1] * 16, "stereo": [0.1, 0.1]})["ok"])

    def test_meta_lists_the_effects(self):
        m = core.Core(self.dir, Backend()).command({"cmd": "meta"})
        self.assertEqual(len(m["patterns"]), 23)
        self.assertEqual(m["layers"], ["heat", "trail"])


if __name__ == "__main__":
    unittest.main()


class Review(unittest.TestCase):
    def test_numbers_snap_to_their_step(self):
        p = patterns.merge(patterns.DEFAULT, {"values": {"stars": {"count": 12.5, "twinkle": 1.234}}})
        self.assertEqual(p["values"]["stars"], {"count": 13, "twinkle": 1.2})
        self.assertIs(type(p["values"]["stars"]["count"]), int)
        self.assertEqual(patterns.clean({"kind": "matrix", "values": {"matrix": {"count": 6.4}}})["values"]["matrix"]["count"], 6)

    def test_odd_values_never_crash(self):
        for kind in patterns.ALL:
            for c in patterns.controls(kind):
                if c.kind == "number":
                    p = patterns.create({"kind": kind, "values": {kind: {c.name: c.lo + c.step / 3}}}, GEO, random.Random(1))
                    p.paint(0.5, effects.State())

    def test_a_failing_effect_does_not_stop_the_lighting(self):
        e = config.merge(config.DEFAULTS, {"stats": {"on": False}, "sound": {"on": False}})
        plan = effects.make_plan(e, BOARD)
        plan.pattern.frame = lambda now, s: 1 / 0
        f = effects.render(BOARD, e, effects.State(), 0, plan)
        self.assertEqual(len(f), len(BOARD.leds))

    def test_tall_keys_make_no_rows_of_their_own(self):
        self.assertEqual(GEO.rows, 6)
        self.assertEqual(GEO.cell(BOARD.by_key["Number Pad +"][0])[1], GEO.cell(BOARD.by_key["Number Pad 7"][0])[1])
