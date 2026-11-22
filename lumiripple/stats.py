"""CPU, RAM and CPU temperature as 0..1. Linux needs no packages; other systems use psutil."""
import glob
import subprocess
import sys


def temp_level(celsius):
    """30 C = empty, 90 C = full."""
    return min(max((celsius - 30) / 60, 0), 1)


def _text(path):
    with open(path) as f:
        return f.read().strip()


class Meter:
    def __init__(self):
        self.linux, self.psutil, self.sensor = sys.platform.startswith("linux"), None, None
        if self.linux:
            self.old = self._cpu()
            for d in glob.glob("/sys/class/hwmon/hwmon*"):
                try:
                    if _text(d + "/name") in ("coretemp", "k10temp", "zenpower", "cpu_thermal"):
                        self.sensor = d + "/temp1_input"
                except OSError:
                    pass
        else:
            try:
                import psutil
                self.psutil = psutil
                psutil.cpu_percent()
            except ImportError:
                pass

    @staticmethod
    def _cpu():
        w = [int(x) for x in _text("/proc/stat").split("\n", 1)[0].split()[1:9]]
        return sum(w), w[3] + w[4]

    def read(self):
        if self.linux:
            new = self._cpu()
            total, idle = new[0] - self.old[0], new[1] - self.old[1]
            self.old = new
            m = {k: int(v.split()[0]) for k, v in (z.split(":") for z in _text("/proc/meminfo").splitlines())}
            try:
                temp = temp_level(int(_text(self.sensor)) / 1000) if self.sensor else None
            except (OSError, ValueError):
                temp = None
            return {"cpu": min(max(1 - idle / total, 0), 1) if total else 0.0, "ram": 1 - m["MemAvailable"] / m["MemTotal"],
                    "cpu_temp": temp}
        if self.psutil:
            return {"cpu": self.psutil.cpu_percent() / 100, "ram": self.psutil.virtual_memory().percent / 100, "cpu_temp": None}
        return {}


def gpu():
    """{"load", "temp", "memory"} or None. NVIDIA through nvidia-smi, AMD on Linux through sysfs."""
    try:
        flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}    # no console window
        out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, check=True, **flags).stdout
        return parse_nvidia(out)
    except (OSError, subprocess.SubprocessError):
        pass
    for d in glob.glob("/sys/class/drm/card*/device"):
        try:
            temps = glob.glob(d + "/hwmon/hwmon*/temp1_input")
            return {"load": min(int(_text(d + "/gpu_busy_percent")) / 100, 1), "temp": int(_text(temps[0])) / 1000 if temps else 30,
                    "memory": min(int(_text(d + "/mem_info_vram_used")) / int(_text(d + "/mem_info_vram_total")), 1)}
        except (OSError, ValueError, ZeroDivisionError):
            continue
    return None


def parse_nvidia(text):
    try:
        load, temp, used, total = (int(x) for x in text.strip().splitlines()[0].split(","))
        return {"load": min(load / 100, 1), "temp": temp, "memory": min(used / total, 1)}
    except (ValueError, IndexError, ZeroDivisionError):
        return None
