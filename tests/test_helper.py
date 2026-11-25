import unittest

from lumiripple import helper


@unittest.skipIf(helper.np is None, "numpy is not installed")
class Levels(unittest.TestCase):
    def tone(self, f, level=.3):
        np = helper.np
        return np.sin(2 * np.pi * f * np.arange(helper.N) / helper.RATE) * level

    def test_silence(self):
        self.assertEqual(helper.levels(helper.np.zeros(helper.N)), [0] * 16)

    def test_tones_land_in_their_band(self):
        for i in range(16):
            v = helper.levels(self.tone((helper.EDGES[i] * helper.EDGES[i + 1]) ** .5))
            self.assertLessEqual(abs(v.index(max(v)) - i), 1 if i < 4 else 0, (i, v))
            self.assertTrue(.6 < max(v) <= 1)

    def test_smoothing_ends_at_zero(self):
        v = helper.smooth([1] * 16, [0] * 16)
        self.assertTrue(0 < v[0] < 1)
        for _ in range(60):
            v = helper.smooth(v, [0] * 16)
        self.assertEqual(v, [0] * 16)


@unittest.skipIf(helper.np is None, "numpy is not installed")
class Stereo(unittest.TestCase):
    def test_channel_level(self):
        np = helper.np
        self.assertEqual(helper.channel_level(np.zeros(100)), 0)
        self.assertAlmostEqual(helper.channel_level(np.ones(100)), 1)
        self.assertAlmostEqual(helper.channel_level(np.ones(100) * 0.1), 0.6, delta=0.01)     # -20 dB

    def test_sound_is_sent_with_left_and_right(self):
        import threading
        import time
        np = helper.np
        sent = []

        class Stream:
            def __init__(self, source):
                self.source = source

            def read(self, n):
                time.sleep(0.01)
                t = np.arange(n) / helper.RATE
                return np.stack([np.sin(2 * np.pi * 440 * t) * 0.8, np.zeros(n)], axis=1)

            def close(self):
                pass

        def call(cmd, **kw):
            if cmd == "needs":
                return {"sound": True, "mic": False, "gpu": False}
            sent.append((cmd, kw))
            return {}
        h = helper.Helper(call)
        h.opener = Stream
        t = threading.Thread(target=h.run, daemon=True)
        t.start()
        time.sleep(1.5)
        h.stop()
        t.join(3)
        audio = [kw for cmd, kw in sent if cmd == "audio"]
        self.assertTrue(audio)
        left, right = audio[-1]["stereo"]
        self.assertGreater(left, 0.5)
        self.assertEqual(right, 0)


@unittest.skipIf(helper.np is None, "numpy is not installed")
class Mono(unittest.TestCase):
    def test_falls_back_to_one_channel(self):
        import sys
        import types
        asked = []

        class Mic:
            def recorder(self, samplerate, channels, blocksize):
                asked.append(channels)
                if channels == 2:
                    raise RuntimeError("only one channel")
                return types.SimpleNamespace(__enter__=lambda: None, __exit__=lambda *a: None)

        fake = types.SimpleNamespace(get_microphone=lambda *a, **k: Mic(), default_speaker=lambda: types.SimpleNamespace(id=1),
                                     default_microphone=lambda: Mic())
        old = sys.modules.get("soundcard")
        sys.modules["soundcard"] = fake
        try:
            st = helper.SoundCard("sound")
        finally:
            if old is None:
                del sys.modules["soundcard"]
            else:
                sys.modules["soundcard"] = old
        self.assertEqual(asked, [2, 1])
        self.assertEqual(st.channels, 1)


class Sources(unittest.TestCase):
    def test_nothing_is_opened_unless_wanted(self):
        opened = []
        h = helper.Helper(lambda cmd, **kw: {"sound": False, "mic": False, "gpu": False})
        h.opener = lambda s: opened.append(s)
        import threading
        import time
        t = threading.Thread(target=h.run, daemon=True)
        t.start()
        time.sleep(1.2)
        h.stop()
        t.join(3)
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
