# Why it is built this way

**On top of OpenRGB instead of own drivers.** Drivers for hundreds of keyboards already exist and are maintained by people who own
the hardware. LumiRipple only needs "set these LEDs" and stays small. The price: no OpenRGB support, no LumiRipple.

**Keys by position, not by legend.** Input systems report where a key is, not what is printed on it. So a key is identified by its
place on a US board, and legends are only labels. A profile therefore works on any layout and any keyboard.

**The keyboard is never grabbed.** A remapper can swallow keys, but if it crashes, the keyboard is dead. LumiRipple only listens.
That is why macro trigger keys keep their normal function.

**Macros store presses and releases with times,** not text. Text needs to know the layout; physical keys do not, and combinations
come out right.

**A wave has a fixed front.** A symmetric ring looked natural, but a wider ring also arrived earlier, so "width" secretly changed
the speed. Now only the tail grows.

**Displays win over waves.** A stat that flickers with every key press is useless.

**Microphone off by default, recording visible.** Nothing that listens should start by itself, and Escape blinks while recording.

**A web page as interface.** The only toolkit that looks the same on three systems without hundreds of megabytes. It needs care:
see [SECURITY.md](SECURITY.md).

**Almost no dependencies.** On Linux the service uses only the Python standard library. Less to install, less to trust.

**Linear sliders.** A curved scale was tried and felt wrong in use.

Ideas not done yet: filtering short touches while typing (only a compositor or a grabbing remapper can do that), a playback display
outside the browser, own effects as plugins, mouse actions in macros.
