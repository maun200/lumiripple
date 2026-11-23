# Installing and removing

## Linux
The installer puts the program, owned by root, into `/opt/lumiripple`, a command into `/usr/local/bin/lumiripple`, and with systemd:

| File | Purpose |
|---|---|
| `/etc/systemd/system/lumiripple.service` | reads keys, renders, types macros (sandboxed) |
| `~/.config/systemd/user/lumiripple-helper.service` | sound levels and GPU values from your session |
| `/etc/udev/rules.d/99-lumiripple.rules` | lets the group `input` use `/dev/uinput` |
| `~/.config/lumiripple/token` | access token for the settings page, readable only by you |

Required: Python 3.10. For sound: numpy and `parec`/`pactl` (pulseaudio-utils, libpulse). Nothing is installed with pip.
Without systemd, run as root: `lumiripple run --token-file ~/.config/lumiripple/token --state /var/lib/lumiripple`.

## macOS
A virtual environment in `~/Library/Application Support/lumiripple`, started by a LaunchAgent. Allow Python under *Accessibility* and
*Input Monitoring*. System sound needs a loopback device such as BlackHole.

## Windows
A virtual environment in `%LOCALAPPDATA%\LumiRipple` and shortcuts in the autostart folder and start menu. No administrator rights.

## Removing
```sh
curl -fsSL https://raw.githubusercontent.com/maun200/lumiripple/main/install.sh | bash -s -- --uninstall
```
```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/maun200/lumiripple/main/install.ps1))) -Uninstall
```
Settings stay: Linux `/var/lib/private/lumiripple`, macOS and Windows next to the token.

## Updating
Run the install command again.
