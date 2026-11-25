"""Runs in the user's session: turns sound into 16 levels and reads the GPU.

Sound is only converted in memory, never stored. The microphone is opened only while it is switched on in the active profile.
"""
import subprocess
import sys
import threading
import time

from . import stats

try:
    import numpy as np
except ImportError:
    np = None

RATE, N, STEP = 22050, 1024, 700
EDGES = [40 * 250 ** (i / 16) for i in range(17)]   # 40 Hz to 10 kHz


def levels(samples):
    """16 levels 0..1 (-50 dB to 0 dB of the strongest tone in each band). samples: N floats -1..1"""
    s = np.abs(np.fft.rfft(samples * np.hanning(N))) * 4 / N
    f = np.fft.rfftfreq(N, 1 / RATE)
    out = []
    for a, b in zip(EDGES, EDGES[1:]):
        db = 20 * np.log10(max(float(s[(f >= a) & (f < b)].max()), 1e-9))
        out.append(0 if db <= -50 else round(min((db + 50) / 50, 1), 3))
    return out


def channel_level(samples):
    """Loudness of one channel 0..1 (-50 dB to 0 dB, as RMS). samples: floats -1..1"""
    rms = float(np.sqrt(np.mean(np.asarray(samples, dtype=float) ** 2))) if len(samples) else 0.0
    db = 20 * np.log10(max(rms, 1e-9))
    return 0 if db <= -50 else round(min((db + 50) / 50, 1), 3)


def smooth(old, new):
    """Rises at once, falls softly."""
    return [0 if (x := max(n, o * .8)) < .02 else round(float(x), 3) for o, n in zip(old, new)]


class Parec:
    """PulseAudio / PipeWire."""

    def __init__(self, source):
        if source == "sound":
            dev = subprocess.check_output(["pactl", "get-default-sink"], text=True, timeout=3).strip() + ".monitor"
        else:
            dev = subprocess.check_output(["pactl", "get-default-source"], text=True, timeout=3).strip()
        self.device, self.channels = dev, 2 if source == "sound" else 1
        self.p = subprocess.Popen(["parec", f"--device={dev}", "--format=s16le", f"--rate={RATE}", f"--channels={self.channels}",
                                   "--latency-msec=30", "--client-name=LumiRipple"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def read(self, n):
        """n frames as an array (n, channels), -1..1."""
        size = n * 2 * self.channels
        data = self.p.stdout.read(size)
        if len(data) < size:
            raise OSError("the sound stream ended")
        return (np.frombuffer(data, "<i2") / 32768).reshape(n, self.channels)

    def close(self):
        self.p.kill()
        self.p.wait()
        self.p.stdout.close()


class SoundCard:
    """Windows (WASAPI loopback) and macOS (microphone; system sound only through a loopback device such as BlackHole)."""

    def __init__(self, source):
        import soundcard
        mic = (soundcard.get_microphone(str(soundcard.default_speaker().id), include_loopback=True) if source == "sound"
               else soundcard.default_microphone())
        self.channels = 2 if source == "sound" else 1
        try:
            self.ctx = mic.recorder(samplerate=RATE, channels=self.channels, blocksize=STEP)
        except Exception:                           # a device without two channels: sound bands still work in mono
            self.channels = 1
            self.ctx = mic.recorder(samplerate=RATE, channels=1, blocksize=STEP)
        self.rec = self.ctx.__enter__()

    def read(self, n):
        return np.asarray(self.rec.record(numframes=n)).reshape(n, self.channels)

    def close(self):
        self.ctx.__exit__(None, None, None)


class Helper:
    def __init__(self, call):
        self.call, self.wanted, self.stopping = call, {}, threading.Event()
        self.errors, self.opener = {}, Parec if sys.platform.startswith("linux") else SoundCard

    def _sound(self, source):
        while not self.stopping.is_set():
            if not self.wanted.get(source):
                self.errors.pop(source, None)
                self.stopping.wait(.5)
                continue
            stream = None
            try:
                stream = self.opener(source)
                buf, last, quiet, check = np.zeros(N), [0] * 16, True, time.monotonic() + 5
                pair, sides = np.zeros((N, 2)), [0, 0]
                self.errors.pop(source, None)
                while self.wanted.get(source) and not self.stopping.is_set():
                    block = np.asarray(stream.read(STEP), dtype=float)
                    block = block.reshape(len(block), -1)
                    buf = np.concatenate((buf, block.mean(axis=1)))[-N:]       # bands from the mix of all channels
                    last = smooth(last, levels(buf))
                    extra = {}
                    if source == "sound" and block.shape[1] == 2:             # left and right for the stereo effect
                        pair = np.concatenate((pair, block))[-N:]
                        sides = smooth(sides, [channel_level(pair[:, 0]), channel_level(pair[:, 1])])
                        extra = {"stereo": sides}
                    was, quiet = quiet, not any(last) and not any(sides)
                    if not (was and quiet):
                        self.call("audio", source=source, levels=last, **extra)
                    if source == "sound" and isinstance(stream, Parec) and time.monotonic() > check:   # default output changed?
                        check = time.monotonic() + 5
                        now = subprocess.check_output(["pactl", "get-default-sink"], text=True, timeout=3).strip() + ".monitor"
                        if now != stream.device:
                            break
            except Exception as e:                  # any sound library may fail in its own way; lighting must go on
                self.errors[source] = f"{source}: {e}"
                self.stopping.wait(5)
            finally:
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass

    def run(self):
        if np is not None:
            for s in ("sound", "mic"):
                threading.Thread(target=self._sound, args=(s,), daemon=True, name=s).start()
        told = ""
        while not self.stopping.is_set():
            try:
                self.wanted = self.call("needs")
                if self.wanted.get("gpu") and (g := stats.gpu()):
                    self.call("gpu", **g)
                err = "; ".join(self.errors.values())[:200] or None if np is not None else "numpy is missing, sound is off"
                if err != told:
                    told = err
                    self.call("helper_status", audio=err)
            except OSError:                         # service restarting
                self.wanted = {}
                self.stopping.wait(2)
            self.stopping.wait(1)

    def stop(self):
        self.stopping.set()
