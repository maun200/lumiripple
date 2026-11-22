# Troubleshooting

Start with `lumiripple doctor`. It prints nothing private, so you can paste it into an issue.

| Problem | What to do |
|---|---|
| no OpenRGB server found | start the SDK server; OpenLinkHub: `enableOpenRGBTargetServer` |
| no per-key keyboard found | OpenRGB must list the keyboard with LEDs named "Key: ..." and a Direct mode |
| keyboard stays on another effect | close vendor software; in OpenLinkHub switch RGB Cluster off |
| "Please open LumiRipple with: lumiripple open" | the page has no token; use that command once |
| no key input on Linux | `journalctl -u lumiripple`; the group `input` must be able to read `/dev/input/event*` |
| no key input on macOS | allow Python under Accessibility and Input Monitoring, then log in again |
| no sound display | numpy and `parec` installed? Linux: `systemctl --user status lumiripple-helper` |
| sound too weak or too strong | Sensitivity |
| macro types nothing on Linux | `ls -l /dev/uinput` must show the group `input`; reboot after installing |
| a key has the wrong position | open an issue with the `doctor` output and your layout |
| switch it off | `sudo systemctl disable --now lumiripple` and `systemctl --user disable --now lumiripple-helper` |
