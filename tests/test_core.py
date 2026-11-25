import json
import os
import tempfile
import time
import unittest

from lumiripple import config, core, stats


class Backend:
    sees_own_events = False

    def __init__(self):
        self.out = []

    def send(self, token, down):
        self.out.append((token, down))

    def label(self, token):
        return str(token)


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.dir, self.back = tempfile.mkdtemp(), Backend()
        self.c = self.new()

    def new(self):
        c = core.Core(self.dir, self.back)
        c.status["input"] = True
        return c

    def do(self, cmd, **kw):
        return self.c.command({"cmd": cmd, **kw})

    def record(self, *seq):
        self.do("record_start")
        t = self.c.recording.start
        for i, (n, tok, d) in enumerate(seq or (("Left Shift", 42, True), ("A", 30, True), ("A", 30, False), ("Left Shift", 42, False))):
            self.c.key(n, tok, d, t + .1 * (i + 1))
        return self.do("record_stop")

    def test_settings_survive_a_restart_and_the_file_is_private(self):
        self.assertTrue(self.do("set", settings={"wave": {"color": [255, 0, 0]}})["ok"])
        self.c.save()
        self.assertEqual(self.new().e["wave"]["color"], [255, 0, 0])
        if os.name == "posix":
            self.assertEqual(os.stat(self.c.file).st_mode & 0o777, 0o600)

    def test_nonsense_is_refused_and_harms_nothing(self):
        for b in (None, [], "x", {}, {"cmd": 5}, {"cmd": "nope"}, {"cmd": "__init__"}, {"cmd": "set"}, {"cmd": "set", "settings": {"pattern": {"values": {"solid": {"color": "red"}}}}},
                  {"cmd": "audio", "source": "sound", "levels": [1]}, {"cmd": "audio", "source": "x", "levels": [0] * 16}, {"cmd": "audio", "source": "mic", "levels": [2] * 16},
                  {"cmd": "gpu", "load": 2, "temp": 1, "memory": 0}, {"cmd": "gpu", "load": 0, "temp": float("nan"), "memory": 0}, {"cmd": "profile_switch", "name": []},
                  {"cmd": "profile_new", "name": " "}, {"cmd": "profile_new", "name": "default"}, {"cmd": "profile_delete", "name": "Default"}, {"cmd": "profile_key", "key": "x"},
                  {"cmd": "profile_key", "key": []}, {"cmd": "macro_set", "name": "x", "speed": 1, "instant": False}, {"cmd": "play_speed", "speed": 99}, {"cmd": "helper_status", "audio": 5}):
            self.assertFalse(self.c.command(b)["ok"], b)
        self.assertEqual(self.do("get")["settings"], config.DEFAULTS)
        json.dumps(self.do("get")), json.dumps(self.do("meta"))

    def test_broken_file_is_moved_aside(self):
        for text in ("{broken", "[]", '{"profiles": {"a": 1}, "active": "a"}', '{"profiles": {"a": {"settings": {"x": 1}, "macros": {}}}, "active": "a"}'):
            with open(self.c.file, "w") as f:
                f.write(text)
            self.assertEqual(self.new().e, config.DEFAULTS, text)
        self.assertTrue(any("broken" in n for n in os.listdir(self.dir)))

    def test_profiles(self):
        self.do("set", settings={"pattern": {"values": {"solid": {"color": [9, 9, 9]}}}})
        self.assertTrue(self.do("profile_new", name="Büro & Spiel")["ok"])
        self.do("set", settings={"pattern": {"values": {"solid": {"color": [1, 1, 1]}}}})
        self.do("profile_rename", name="Default", title="Daily")
        self.assertFalse(self.do("profile_rename", name="Daily", title="büro & spiel")["ok"])
        self.assertTrue(self.do("profile_rename", name="Büro & Spiel", title="Game")["ok"])
        self.assertEqual((self.c.active, list(self.c.data["profiles"])), ("Game", ["Daily", "Game"]))
        self.do("profile_reset", everything=False)
        self.assertEqual(self.c.e, config.DEFAULTS)
        self.do("profile_switch", name="Daily")
        self.assertEqual(self.c.e["pattern"]["values"]["solid"]["color"], [9, 9, 9])
        self.assertTrue(self.do("profile_delete", name="Game")["ok"])

    def test_profile_key_cycles(self):
        self.do("profile_new", name="Two")
        self.do("profile_key", key="Pause/Break")
        for want in ("Default", "Two"):
            self.c.key("Pause/Break", 119, True, 1.0)
            self.c.key("Pause/Break", 119, False, 1.1)
            self.assertEqual(self.c.active, want)

    def test_without_recording_no_key_is_kept(self):
        for tok in (30, 31, 32):
            self.c.key("A", tok, True, 1.0)
            self.c.key("A", tok, False, 1.1)
        self.c.save()
        self.assertIsNone(self.c.draft)
        with open(self.c.file) as f:
            self.assertEqual([p["macros"] for p in json.load(f)["profiles"].values()], [{}])

    def test_macro_from_recording_to_playback(self):
        self.assertEqual(self.record()["count"], 2)
        self.assertTrue(self.do("macro_save", name="Hello", trigger="Pause/Break")["ok"])
        g = self.do("get")
        self.assertEqual(g["macros"], [{"name": "Hello", "trigger": "Pause/Break", "speed": 1.0, "instant": False}])
        self.assertNotIn("events", json.dumps(g))
        self.c.key("Pause/Break", 119, True, 5.0)
        self.c.tick(9.0)
        self.assertEqual(self.back.out, [(42, True), (30, True), (30, False), (42, False)])
        self.c.save()
        self.assertEqual(self.new().p["macros"]["Hello"]["events"][0][1:], [42, True])

    def test_macro_rules(self):
        self.record()
        for kw in (dict(name="", trigger="F13"), dict(name="x", trigger="nokey"), dict(name="x", trigger=None)):
            self.assertFalse(self.do("macro_save", **kw)["ok"], kw)
        self.assertTrue(self.do("macro_save", name="x", trigger="F13")["ok"])
        self.assertFalse(self.do("macro_save", name="y", trigger="F14")["ok"])           # no recording any more
        self.record()
        self.assertFalse(self.do("macro_save", name="y", trigger="F13")["ok"])           # key in use
        self.assertFalse(self.do("macro_save", name="x", trigger="F14")["ok"])           # name in use
        self.assertTrue(self.do("macro_set", name="x", speed=2, instant=True)["ok"])
        self.c.key("F13", 183, True, 1.0)
        self.assertLess(self.c.player.view(1.0, str)["total"], .1)
        self.assertTrue(self.do("play_cancel")["ok"])
        self.assertTrue(self.do("macro_delete", name="x")["ok"])

    def test_macro_does_not_retrigger_while_held_or_playing(self):
        self.record()
        self.do("macro_save", name="m", trigger="Pause/Break")
        self.c.key("Pause/Break", 119, True, 1.0)
        self.c.tick(1.0)
        self.c.key("Pause/Break", 119, True, 1.05)
        self.c.tick(9.0)
        self.assertEqual(len(self.back.out), 4)

    def test_own_events_are_ignored_where_the_system_echoes_them(self):
        self.record()
        self.do("macro_save", name="m", trigger="F13")
        self.back.sees_own_events = True
        self.c.state.pressed.clear()
        self.c.key("F13", "x", True, 1.0)
        self.c.key("A", "x", True, 1.1)
        self.assertNotIn("A", self.c.state.pressed)

    def test_recording_ends_on_switch_and_needs_input(self):
        self.do("record_start")
        self.do("profile_new", name="Other")
        self.assertIsNone(self.c.recording)
        self.c.status["input"] = False
        self.assertFalse(self.do("record_start")["ok"])

    def test_pressed_keys_and_minimum_press(self):
        self.c.key("A", 30, True, 1.0)
        self.c.key("A", 30, True, 1.2)
        self.assertEqual((len(self.c.state.waves), self.c.state.pressed), (1, {"A": (1.0, None)}))
        self.c.key("A", 30, False, 2.0)
        self.c.tick(9.0)
        self.assertEqual((self.c.state.pressed, self.c.state.waves), ({}, []))
        self.do("set", settings={"press": {"on": True, "min_ms": 40}})
        self.c.key("A", 30, True, 10.0)
        self.assertAlmostEqual(self.c.due(10.0), .04)
        self.c.key("A", 30, False, 10.02)
        self.c.tick(10.1)
        self.assertEqual(self.c.state.waves, [])
        self.c.key("A", 30, True, 11.0)
        self.c.tick(11.05)
        self.assertEqual(len(self.c.state.waves), 1)
        self.c.release_all(11.1)
        self.assertEqual(self.c.state.pressed, {"A": (11.05, 11.1)})
        for i in range(50):
            self.c._counts("A", 12.0)
        self.assertLessEqual(len(self.c.state.waves), 12)

    def test_unknown_keys_are_harmless(self):
        for n in (None, "F13", "no such key"):
            self.c.key(n, 999, True, 1.0)
            self.c.key(n, 999, False, 1.1)
        self.assertEqual(self.c.state.waves, [])

    def test_microphone_only_when_wanted_and_levels_expire(self):
        self.assertEqual([self.do("needs")[k] for k in ("sound", "mic", "gpu")], [True, False, True])
        self.do("set", settings={"mic": {"on": True}, "stats": {"items": []}})
        self.assertEqual([self.do("needs")[k] for k in ("sound", "mic", "gpu")], [True, True, False])
        self.assertTrue(self.do("audio", source="mic", levels=[.5] * 16)["ok"])
        self.assertTrue(self.do("gpu", load=.5, temp=60, memory=.25)["ok"])
        self.assertEqual((self.c.state.mic, self.c.state.gpu_temp), ([.5] * 16, .5))
        self.c.tick(time.monotonic() + 6)
        self.assertEqual((self.c.state.mic, self.c.state.gpu), (None, None))


class Stats(unittest.TestCase):
    def test_values_are_shares(self):
        for v in stats.Meter().read().values():
            self.assertTrue(v is None or 0 <= v <= 1)

    def test_nvidia(self):
        self.assertEqual(stats.parse_nvidia("19, 28, 1536, 6144\n"), {"load": .19, "temp": 28, "memory": .25})
        for bad in ("", "N/A, 1, 2, 3", "1, 2", "1, 2, 3, 0"):
            self.assertIsNone(stats.parse_nvidia(bad))


if __name__ == "__main__":
    unittest.main()
