#!/bin/bash
# Print a markdown table of the actual state of every clone under upstream/ (remote, ref, commit, commit date).
cd "$(dirname "$0")/../upstream"
echo "| Directory | Remote | Checked-out ref | Commit | Commit date |"; echo "|---|---|---|---|---|"
for d in */; do d=${d%/}; [ -d "$d/.git" ] || continue
  ref=$(git -C $d describe --tags --exact-match 2>/dev/null || git -C $d rev-parse --abbrev-ref HEAD)
  echo "| $d | $(git -C $d remote get-url origin) | $ref | \`$(git -C $d rev-parse HEAD)\` | $(git -C $d log -1 --format=%cd --date=short) |"; done
