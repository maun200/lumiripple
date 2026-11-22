#!/usr/bin/env bash
# LumiRipple installer for Linux and macOS.
#   curl -fsSL https://raw.githubusercontent.com/OWNER/lumiripple/main/install.sh | bash
# Remove it again with:  curl -fsSL .../install.sh | bash -s -- --uninstall
# Everything is inside functions, so a download that breaks off halfway does nothing.
set -euo pipefail

REPO="${LUMIRIPPLE_REPO:-https://github.com/OWNER/lumiripple}"
REF="${LUMIRIPPLE_REF:-main}"
OPT=/opt/lumiripple

say() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf 'Note: %s\n' "$*" >&2; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
root() { if [ "$(id -u)" = 0 ]; then "$@"; elif have sudo; then sudo "$@"; elif have doas; then doas "$@"; else die "please install sudo or run as root: $*"; fi; }

usage() {
  cat <<'TEXT'
usage: install.sh [--uninstall | --help]
Environment: LUMIRIPPLE_REPO (download address), LUMIRIPPLE_REF (branch or tag)
TEXT
}

find_source() {
  local here=""
  if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; fi
  if [ -n "$here" ] && [ -f "$here/lumiripple/__main__.py" ]; then SRC="$here"; return; fi
  case "$REPO" in */OWNER/*) die "this copy has no download address yet; run it from a checkout or set LUMIRIPPLE_REPO" ;; esac
  have curl || die "curl is needed"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  say "Downloading LumiRipple ($REF)"
  curl -fsSL "$REPO/archive/$REF.tar.gz" | tar -xz -C "$TMP" --strip-components=1
  [ -f "$TMP/lumiripple/__main__.py" ] || die "the download is incomplete"
  SRC="$TMP"
}

check_python() {
  have python3 || return 1
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'
}

linux_packages() {
  local id="" like=""
  if [ -r /etc/os-release ]; then id="$(. /etc/os-release; echo "${ID:-}")"; like="$(. /etc/os-release; echo "${ID_LIKE:-}")"; fi
  say "Installing packages (python3, numpy, sound tools)"
  case " $id $like " in
    *" debian "*|*" ubuntu "*) root apt-get update -qq; root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-numpy pulseaudio-utils >/dev/null ;;
    *" fedora "*|*" rhel "*) root dnf install -y -q python3 python3-numpy pulseaudio-utils >/dev/null ;;
    *" arch "*) root pacman -S --needed --noconfirm python python-numpy libpulse >/dev/null ;;
    *suse*) root zypper -n -q install python3 python3-numpy pulseaudio-utils >/dev/null ;;
    *" alpine "*) root apk add -q python3 py3-numpy pulseaudio-utils ;;
    *" void "*) root xbps-install -Sy python3 python3-numpy pulseaudio-utils >/dev/null ;;
    *) warn "unknown distribution; please install python3, numpy and parec/pactl yourself (sound needs the last two)" ;;
  esac || warn "some packages could not be installed; lighting works without numpy, sound does not"
}

make_token() {
  local mask
  mask="$(umask)"
  umask 077
  mkdir -p "$1"
  if [ ! -s "$1/token" ]; then python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' > "$1/token"; fi
  umask "$mask"
}

install_linux() {
  [ "$(id -u)" != 0 ] || [ -n "${LUMIRIPPLE_ALLOW_ROOT:-}" ] || die "please run this as your normal user; it asks for administrator rights itself"
  if ! { check_python && python3 -c 'import numpy' 2>/dev/null && have parec; }; then linux_packages; fi
  check_python || die "Python 3.10 or newer is needed"
  find_source
  say "Installing to $OPT"
  root rm -rf "$OPT/lumiripple"
  root mkdir -p "$OPT" /usr/local/bin
  root cp -R "$SRC/lumiripple" "$OPT/"
  printf '#!/usr/bin/env python3\nimport sys\nsys.path.insert(0, "%s")\nsys.dont_write_bytecode = True\nfrom lumiripple.__main__ import main\nsys.exit(main())\n' "$OPT" | root tee "$OPT/lumiripple-service" >/dev/null
  # Owned by root: no program of the user may change code that reads the keyboard.
  root chown -R 0:0 "$OPT"
  root chmod -R u=rwX,go=rX "$OPT"
  root chmod 755 "$OPT/lumiripple-service"
  root ln -sf "$OPT/lumiripple-service" /usr/local/bin/lumiripple
  local cfg="${XDG_CONFIG_HOME:-$HOME/.config}/lumiripple"
  make_token "$cfg"
  mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/scalable/apps"
  cp "$SRC/packaging/lumiripple.desktop" "$HOME/.local/share/applications/"
  cp "$SRC/lumiripple/static/icon.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/lumiripple.svg"
  if [ -d /run/systemd/system ]; then
    root cp "$SRC/packaging/99-lumiripple.rules" /etc/udev/rules.d/
    root modprobe uinput 2>/dev/null || true
    root udevadm control --reload-rules 2>/dev/null || true
    root udevadm trigger --subsystem-match=misc 2>/dev/null || true
    sed "s|@TOKEN@|$cfg/token|" "$SRC/packaging/lumiripple.service" | root tee /etc/systemd/system/lumiripple.service >/dev/null
    mkdir -p "$HOME/.config/systemd/user"
    cp "$SRC/packaging/lumiripple-helper.service" "$HOME/.config/systemd/user/"
    root systemctl daemon-reload
    root systemctl enable -q lumiripple.service
    root systemctl restart lumiripple.service
    { systemctl --user daemon-reload && systemctl --user enable -q lumiripple-helper && systemctl --user restart lumiripple-helper; } || warn "the sound helper starts at your next login"
  else
    warn "no systemd here. Start LumiRipple as root from your init system:"
    warn "  lumiripple run --token-file $cfg/token --state /var/lib/lumiripple"
  fi
}

install_macos() {
  check_python || { have brew && brew install python; } || die "Python 3.10 or newer is needed (https://www.python.org or: brew install python)"
  find_source
  local base="$HOME/Library/Application Support/lumiripple" agent="$HOME/Library/LaunchAgents/org.lumiripple.plist"
  say "Installing to $base"
  mkdir -p "$base/app" "$HOME/Library/LaunchAgents" "$HOME/.local/bin"
  rm -rf "$base/app/lumiripple"
  cp -R "$SRC/lumiripple" "$base/app/"
  [ -x "$base/venv/bin/python" ] || python3 -m venv "$base/venv"
  "$base/venv/bin/python" -m pip install -q --upgrade pip
  "$base/venv/bin/python" -m pip install -q pynput psutil numpy soundcard
  printf '#!/bin/sh\ncd "%s/app" && exec "%s/venv/bin/python" -m lumiripple "$@"\n' "$base" "$base" > "$HOME/.local/bin/lumiripple"
  chmod 755 "$HOME/.local/bin/lumiripple"
  cat > "$agent" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>org.lumiripple</string>
<key>ProgramArguments</key><array><string>$HOME/.local/bin/lumiripple</string><string>run</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
</dict></plist>
PLIST
  launchctl bootout "gui/$(id -u)/org.lumiripple" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$agent"
  warn "allow key input: System Settings > Privacy & Security > Accessibility and Input Monitoring > Python"
  warn "macOS has no system sound capture; the sound display needs a loopback device such as BlackHole"
}

uninstall() {
  if [ "$(uname -s)" = Darwin ]; then
    launchctl bootout "gui/$(id -u)/org.lumiripple" 2>/dev/null || true
    rm -rf "$HOME/Library/Application Support/lumiripple/app" "$HOME/Library/Application Support/lumiripple/venv"
    rm -f "$HOME/Library/LaunchAgents/org.lumiripple.plist" "$HOME/.local/bin/lumiripple"
  else
    systemctl --user disable -q --now lumiripple-helper 2>/dev/null || true
    if [ -d /run/systemd/system ]; then root systemctl disable -q --now lumiripple.service 2>/dev/null || true; fi
    root rm -rf "$OPT" /usr/local/bin/lumiripple /etc/systemd/system/lumiripple.service /etc/udev/rules.d/99-lumiripple.rules
    rm -f "$HOME/.config/systemd/user/lumiripple-helper.service" "$HOME/.local/share/applications/lumiripple.desktop" "$HOME/.local/share/icons/hicolor/scalable/apps/lumiripple.svg"
    if [ -d /run/systemd/system ]; then root systemctl daemon-reload; fi
  fi
  say "LumiRipple is removed. Your settings were kept (Linux: /var/lib/private/lumiripple and ~/.config/lumiripple)."
}

main() {
  case "${1:-}" in
    "") ;;
    --uninstall) uninstall; return ;;
    -h|--help) usage; return ;;
    *) usage >&2; exit 2 ;;                        # never install because of a typo
  esac
  case "$(uname -s)" in
    Linux) install_linux ;;
    Darwin) install_macos ;;
    *) die "this script is for Linux and macOS; on Windows use install.ps1" ;;
  esac
  say "Done. Start the OpenRGB SDK server (or OpenLinkHub with enableOpenRGBTargetServer), then run: lumiripple open"
  say "Something wrong? Run: lumiripple doctor"
}
main "$@"
