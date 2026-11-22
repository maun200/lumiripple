"""Physical keyboard model.

A key is identified by its position on a US board ("Z" is always the key left of "X"), because that is what
input APIs report. What is printed on the key cap ("Y" on a German board) is only a label.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Key:
    name: str
    x: float
    y: float
    w: float = 1.0
    h: float = 1.0


def _row(y, *items):
    out, x = [], 0.0
    for it in items:
        if isinstance(it, (int, float)):      # gap
            x += it
            continue
        name, w = it if isinstance(it, tuple) else (it, 1.0)
        out.append(Key(name, x, y, w))
        x += w
    return out


_NP = "Number Pad "
KEYS = [
    *_row(0, "Escape", 1, "F1", "F2", "F3", "F4", .5, "F5", "F6", "F7", "F8", .5, "F9", "F10", "F11", "F12", .25,
          "Print Screen", "Scroll Lock", "Pause/Break", .25, "Media Stop", "Media Previous", "Media Play/Pause", "Media Next"),
    *_row(1.25, "`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", ("Backspace", 2), .25,
          "Insert", "Home", "Page Up", .25, "Num Lock", _NP + "/", _NP + "*", _NP + "-"),
    *_row(2.25, ("Tab", 1.5), *"QWERTYUIOP", "[", "]", ("\\ (ANSI)", 1.5), .25, "Delete", "End", "Page Down", .25,
          _NP + "7", _NP + "8", _NP + "9"),
    Key(_NP + "+", 21.5, 2.25, 1, 2),
    *_row(3.25, ("Caps Lock", 1.75), *"ASDFGHJKL", ";", "'", ("Enter", 2.25), 3.5, _NP + "4", _NP + "5", _NP + "6"),
    Key("#", 12.75, 3.25),
    *_row(4.25, ("Left Shift", 2.25), *"ZXCVBNM", ",", ".", "/", ("Right Shift", 2.75), 1.25, "Up Arrow", 1.25,
          _NP + "1", _NP + "2", _NP + "3"),
    Key("\\ (ISO)", 1.25, 4.25),
    Key(_NP + "Enter", 21.5, 4.25, 1, 2),
    *_row(5.25, ("Left Control", 1.25), ("Left Windows", 1.25), ("Left Alt", 1.25), ("Space", 6.25), ("Right Alt", 1.25),
          ("Right Fn", 1.25), ("Menu", 1.25), ("Right Control", 1.25), .25, "Left Arrow", "Down Arrow", "Right Arrow", .25,
          (_NP + "0", 2), _NP + "."),
    Key("Right Windows", 11.25, 5.25, 1.25),
    Key("Media Mute", 21.5, -1.25),
]
BY_NAME = {k.name: k for k in KEYS}

# LED names other layouts use for the same physical key.
ALIASES = {
    "Enter (ISO)": "Enter", "Left Fn": "Right Fn", "\\": "\\ (ANSI)", "< >": "\\ (ISO)",
    "Ä": "'", "Ö": ";", "Ü": "[", "ß": "-", "´": "=", "´/¨": "=", "´ `": "=", "^": "`", "§ ½": "`", "Å": "[", "¨ ^": "]", "' *": "#",
    "Ö Æ": ";", "Ä Ø": "'", "Ñ": ";", "²": "`", "é": "2", "è": "7", "ç": "9", "à": "0", "ù": "'", "$": "]", "*": "#",
    "¿/¡": "=", "+ ?": "-",
}

_LETTERS_ROW = [list("QWERTYUIOP") + ["[", "]"], list("ASDFGHJKL") + [";", "'", "#"], ["\\ (ISO)"] + list("ZXCVBNM") + [",", ".", "/"]]
_DIGITS = ["`", *"1234567890", "-", "="]
AREAS = {
    "numpad": ("Number pad and media keys", {k.name for k in KEYS if k.x >= 18.5 and k.y >= 0}),
    "letters": ("Letters", {n for r in _LETTERS_ROW for n in r}),
    "digits": ("Number row", set(_DIGITS)),
    "main": ("Whole main block", {k.name for k in KEYS if k.x + k.w <= 15.01 and k.y >= 1}),
    "fkeys": ("Function keys", {f"F{i}" for i in range(1, 13)}),
    "nav": ("Navigation and arrows", {k.name for k in KEYS if 15.2 <= k.x < 18.3}),
    "all": ("Whole keyboard", None),
}
GROUPS = {"WASD": ["W", "A", "S", "D"], "Arrows": ["Up Arrow", "Left Arrow", "Down Arrow", "Right Arrow"],
          "Digits": list("1234567890"), "F keys": [f"F{i}" for i in range(1, 13)]}


def rows():
    """Key names by row, left to right. 'Neighbouring keys' means neighbours in these lists."""
    by_y = {}
    for k in KEYS:
        by_y.setdefault(k.y, []).append(k)
    return [[k.name for k in sorted(by_y[y], key=lambda k: k.x)] for y in sorted(by_y)]


# Linux input event codes -> key
EVDEV = {
    1: "Escape", **{59 + i: f"F{i + 1}" for i in range(10)}, 87: "F11", 88: "F12", 99: "Print Screen", 70: "Scroll Lock",
    119: "Pause/Break", 41: "`", **{2 + i: c for i, c in enumerate("1234567890")}, 12: "-", 13: "=", 14: "Backspace",
    15: "Tab", **{16 + i: c for i, c in enumerate("QWERTYUIOP")}, 26: "[", 27: "]", 43: "\\ (ANSI)", 58: "Caps Lock",
    **{30 + i: c for i, c in enumerate("ASDFGHJKL")}, 39: ";", 40: "'", 28: "Enter", 42: "Left Shift", 86: "\\ (ISO)",
    **{44 + i: c for i, c in enumerate("ZXCVBNM")}, 51: ",", 52: ".", 53: "/", 54: "Right Shift", 29: "Left Control",
    125: "Left Windows", 56: "Left Alt", 57: "Space", 100: "Right Alt", 126: "Right Windows", 127: "Menu", 97: "Right Control",
    110: "Insert", 102: "Home", 104: "Page Up", 111: "Delete", 107: "End", 109: "Page Down", 103: "Up Arrow", 105: "Left Arrow",
    108: "Down Arrow", 106: "Right Arrow", 69: "Num Lock", 98: _NP + "/", 55: _NP + "*", 74: _NP + "-", 71: _NP + "7",
    72: _NP + "8", 73: _NP + "9", 78: _NP + "+", 75: _NP + "4", 76: _NP + "5", 77: _NP + "6", 79: _NP + "1", 80: _NP + "2",
    81: _NP + "3", 96: _NP + "Enter", 82: _NP + "0", 83: _NP + ".", 113: "Media Mute", 166: "Media Stop", 165: "Media Previous",
    164: "Media Play/Pause", 163: "Media Next", **{183 + i: f"F{13 + i}" for i in range(12)},
}
# Windows set-1 scan codes equal the Linux codes for the basic block; extended keys carry the 0x100 flag.
WIN_SCAN = {c: n for c, n in EVDEV.items() if c < 89}
WIN_SCAN.update({0x11D: "Right Control", 0x138: "Right Alt", 0x147: "Home", 0x148: "Up Arrow", 0x149: "Page Up", 0x14B: "Left Arrow",
                 0x14D: "Right Arrow", 0x14F: "End", 0x150: "Down Arrow", 0x151: "Page Down", 0x152: "Insert", 0x153: "Delete",
                 0x15B: "Left Windows", 0x15C: "Right Windows", 0x15D: "Menu", 0x11C: _NP + "Enter", 0x135: _NP + "/",
                 0x137: "Print Screen", 0x145: "Num Lock", 0x45: "Pause/Break", 0x120: "Media Mute", 0x124: "Media Stop",
                 0x110: "Media Previous", 0x122: "Media Play/Pause", 0x119: "Media Next"})
# macOS virtual key codes
MAC = dict(zip(
    [53, 122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111, 105, 107, 113, 50, 18, 19, 20, 21, 23, 22, 26, 28, 25, 29, 27, 24,
     51, 48, 12, 13, 14, 15, 17, 16, 32, 34, 31, 35, 33, 30, 42, 57, 0, 1, 2, 3, 5, 4, 38, 40, 37, 41, 39, 36, 56, 10, 6, 7, 8, 9,
     11, 45, 46, 43, 47, 44, 60, 59, 55, 58, 49, 61, 54, 110, 62, 114, 115, 116, 117, 119, 121, 126, 123, 125, 124, 71, 75, 67, 78,
     89, 91, 92, 69, 86, 87, 88, 83, 84, 85, 76, 82, 65],
    ["Escape", *[f"F{i}" for i in range(1, 13)], "Print Screen", "Scroll Lock", "Pause/Break", "`", *"1234567890", "-", "=",
     "Backspace", "Tab", *"QWERTYUIOP", "[", "]", "\\ (ANSI)", "Caps Lock", *"ASDFGHJKL", ";", "'", "Enter", "Left Shift",
     "\\ (ISO)", *"ZXCVBNM", ",", ".", "/", "Right Shift", "Left Control", "Left Windows", "Left Alt", "Space", "Right Alt",
     "Right Windows", "Menu", "Right Control", "Insert", "Home", "Page Up", "Delete", "End", "Page Down", "Up Arrow", "Left Arrow",
     "Down Arrow", "Right Arrow", "Num Lock", _NP + "/", _NP + "*", _NP + "-", _NP + "7", _NP + "8", _NP + "9", _NP + "+",
     _NP + "4", _NP + "5", _NP + "6", _NP + "1", _NP + "2", _NP + "3", _NP + "Enter", _NP + "0", _NP + "."]))
