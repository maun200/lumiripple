#!/usr/bin/env bash
# Put the real GitHub account into all links:  scripts/set-owner.sh my-account
set -euo pipefail
[ $# = 1 ] && [[ "$1" =~ ^[A-Za-z0-9-]+$ ]] || { echo "usage: $0 github-account" >&2; exit 1; }
cd "$(dirname "$0")/.."
grep -rlE 'OWNER/lumiripple' --exclude-dir=.git --exclude=set-owner.sh . | while read -r f; do
  sed "s#OWNER/lumiripple#$1/lumiripple#g" "$f" > "$f.new" && cat "$f.new" > "$f" && rm "$f.new"
done
echo "done, please check: git diff --stat"
