# How it works

```
keyboard ── key events ──> LumiRipple service ── frames (max. 33/s) ──> OpenRGB or OpenLinkHub ──> keyboard
                             ^            ^
     settings page (browser) ┘            └ helper: 16 sound levels, left/right, GPU values
```

| File | Job |
|---|---|
| `keys.py` | physical key model, key codes per system, areas |
| `openrgb.py` | SDK client (protocol 0–4), recognises QWERTY, QWERTZ and AZERTY by where the LEDs sit |
| `effects.py` | renders one frame; pure functions |
| `patterns/` | the effects: each describes its own controls, the page builds itself from that |
| `core.py` | state and all commands; no threads, no hardware |
| `engine.py` | loop, connections, saving |
| `inputs.py` | Linux: evdev and uinput directly; Windows and macOS: pynput |
| `helper.py`, `stats.py` | sound, GPU, CPU, RAM |
| `web.py`, `static/` | settings page |
| `macros.py`, `config.py` | recording and playing; defaults and strict validation |

A frame is sent only when it differs from the last one. Servers may blank the keyboard after a change, so LumiRipple paints again
a little later.
