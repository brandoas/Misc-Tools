#!/usr/bin/env bash
# Copy the chain prompts and INPUT-SPEC.md into each course repo's Grading/prompts/.
# Usage: ./sync-prompts.sh          copy
#        ./sync-prompts.sh --check  report drift, change nothing
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
src=("$here"/prompts/chain/*.md "$here/INPUT-SPEC.md")
drift=0
for repo in ITS-3100-Devel ITS-4750-Infrastructure; do
  dst="$root/$repo/Grading/prompts"
  [ -d "$root/$repo" ] || { echo "skip $repo: not checked out"; continue; }
  mkdir -p "$dst"
  for f in "${src[@]}"; do
    t="$dst/$(basename "$f")"
    if ! cmp -s "$f" "$t"; then
      drift=1
      if [ "${1:-}" = "--check" ]; then echo "DRIFT $repo/Grading/prompts/$(basename "$f")"
      else cp "$f" "$t"; echo "copied $(basename "$f") -> $repo"; fi
    fi
  done
done
[ "${1:-}" = "--check" ] && [ $drift = 0 ] && echo "in sync"
exit 0
