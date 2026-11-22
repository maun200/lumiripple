#!/usr/bin/env bash
# Look for personal traces before publishing: authors, time zones, session links, home folders, serial numbers.
# More words to look for can be listed, one per line, in the file named by LUMIRIPPLE_PRIVATE_WORDS.
# This script only reads.
set -euo pipefail
cd "$(dirname "$0")/.."
bad=0
fail() { echo "PRIVACY: $*" >&2; bad=1; }

who="LumiRipple contributors <noreply@lumiripple.invalid>"
others="$(git log --all --format='%an <%ae> / %cn <%ce>' | grep -vxF "$who / $who" || true)"
[ -z "$others" ] || fail "other authors in history: $others"
zones="$(git log --all --format='%ad %cd' --date=format:%z | grep -vx '+0000 +0000' || true)"
[ -z "$zones" ] || fail "commit dates are not in UTC"
if git log --all --format=%B | grep -niE 'session_|claude\.ai/code'; then fail "session link in a commit message"; fi
if git grep -nIE '/home/[a-z]|/Users/[a-z]|C:\\Users|[A-F0-9]{32}' -- . ':!scripts/check-privacy.sh'; then fail "personal path or serial number"; fi
if [ -n "${LUMIRIPPLE_PRIVATE_WORDS:-}" ]; then
  while read -r w; do
    [ -n "$w" ] || continue
    if git grep -qiIF -e "$w"; then fail "a private word is in the files"; fi
    if git log --all -p | grep -qiF -e "$w"; then fail "a private word is in the history"; fi
  done < "$LUMIRIPPLE_PRIVATE_WORDS"
fi
[ $bad = 0 ] && echo "no personal traces found"
exit $bad
