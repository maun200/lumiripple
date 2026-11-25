# Settings

Everything below belongs to a profile. Changes apply at once and are saved by themselves.

**Colors.** Every color button opens the same editor: color wheel (hue), square (saturation and brightness), presets, color code.
Black means off. Where a gradient makes sense there is a switch for it: 2 to 8 colors, for areas also a direction and a motion
of up to two turns per second. On waves and pressed keys the gradient runs over time.

| Section | Setting | Range | Default |
|---|---|---|---|
| Profile | Overall brightness | 0–100 % | 100 % |
| | Profile key | any key | none |
| Effect | one of 23 effects; each has its own settings, shown on the page | | Color / gradient, dark blue |
| | with two or more colors: a brightness for each color | 0–100 % | 100 % |
| Typing layers | Heat map, Trail: on top of any effect, same settings as the effects | | off |
| Wave | Speed | 0.5–40 keys/s | 9 |
| | Width: length of the tail, never changes the speed | 0.15–5 keys | 0.9 |
| | Fade | 0.2–5 s | 1.4 |
| Pressed key | Fade out | 0–3 s | 0.35 |
| | Also over displays | on/off | on |
| | Ignore short touches, minimum | 5–200 ms | off, 30 |
| Highlighted keys | up to 24 entries; own key color and/or own wave color | | none |
| Other lights | own color per light | | follow the effect |
| PC stats | up to 12 displays: value, first key, number of keys (1–24) | | CPU F1–F4, GPU F5–F8, RAM F9–F12 |
| Sound | Sensitivity, areas | 0.1–5 | 1, number pad |
| Microphone | the same; off until you switch it on | | letters |
| Macros | trigger key, speed, instant | 0.25–4 | 1 |

One key alone as a stat display shows the value as a color. Temperatures run from 30 °C (empty) to 90 °C (full).

**Priority on one key:** pressed key (if "over displays"), PC stats, highlighted keys and other lights, sound or microphone
(the stronger one), wave, typing layers, effect.

**Effects.** Each effect brings its own controls. Effects that can stand still (rainbow, spin, watercolor) do so at speed 0.
Music effects use the computer's sound, never the microphone; the stereo effect needs a two-channel output. A color of 1 or more
never dims to fully off, because an LED at 0 looks brighter than a faint one when its neighbours shine. Brightness 0 is off.
Typing effects only count key presses in memory; nothing about what you type is stored.

**Macros** replay physical keys, so they follow your keyboard layout. A trigger key keeps its normal function, because LumiRipple
never blocks the keyboard. Good triggers: Pause, Scroll Lock, F13 to F24. While recording, Escape blinks red.

## Command line
`lumiripple run` (service) · `helper` · `open` (settings page) · `doctor` (checks). `run` knows `--server HOST:PORT` (repeatable),
`--demo`, `--port`, `--state`, `--token-file`, `--no-helper`.
