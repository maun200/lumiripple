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
