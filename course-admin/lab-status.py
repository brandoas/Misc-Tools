#!/usr/bin/env python3
"""List open lab issues across the course repos.

Run this for a status report. It scans every FEEDBACK.md in the course projects
and lists the items still waiting to be acted on, so a note written while
grading in the autumn surfaces again when the lab is rebuilt in the spring.

    python lab-status.py                 # everything still open
    python lab-status.py --course 3100   # one course
    python lab-status.py --all           # include closed items

**An item has to be tagged.** Inferring one from headings does not work: these
files are narrative, and a first pass that treated every section heading as an
issue returned 84 of them, nearly all prose like "What changed structurally".

Tag anything actionable with `TODO(spring)`, on its own line or inside the
paragraph that explains it. The scanner also picks up markers already present in
the existing files, listed in ACTION below.

Close an item the way the existing entries are closed: strike the heading
through with ~~tildes~~, or add FIXED, RESOLVED, DECIDED or DONE on the tagged
line. Nothing here writes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# The feedback files carry em dashes and curly quotes, and a Windows console
# defaults to cp1252, which cannot encode them. Print UTF-8 and replace what it
# still cannot show, rather than dying halfway through a report.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: Course repos are discovered, not listed, so a new course needs no code
#: change. Any sibling directory holding at least one FEEDBACK.md counts, and
#: the short key is the first number in its name.
def discover(root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        try:
            next(d.rglob("FEEDBACK.md"))
        except StopIteration:
            continue
        m = re.search(r"(\d{3,4})", d.name)
        found[m.group(1) if m else d.name.lower()] = d.name
    return found

ACTION = re.compile(
    r"TODO\([^)]*\)"
    r"|DECISION NEEDED"
    r"|Change for (?:Spring|Fall|next year)"
    r"|^\s*OPEN:"
    r"|needs? (?:a )?(?:rewrite|rewording|fixing)",
    re.M | re.I)

CLOSED = re.compile(
    r"~~.+~~|(?<![A-Za-z])(FIXED|RESOLVED|DECIDED|DONE|WONTFIX)(?![A-Za-z])")


def find_root() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / "ITS-3100-Devel").is_dir():
            return p
    return Path(__file__).resolve().parents[2]


def scan(root: Path, repos: dict[str, str], courses: list[str],
         show_all: bool) -> int:
    open_count = 0
    for key in courses:
        repo = root / repos[key]
        files = sorted(repo.rglob("FEEDBACK.md"))
        header_shown = False

        for f in files:
            text = f.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            items = []
            for m in ACTION.finditer(text):
                n = text[:m.start()].count("\n")
                raw = lines[n].strip()
                # Show the nearest heading above, so an item reads in context.
                context = ""
                if not raw.startswith("#"):
                    for back in range(n, max(n - 40, -1), -1):
                        if lines[back].startswith("#"):
                            context = lines[back].lstrip("# ").strip()
                            break
                closed = bool(CLOSED.search(raw))
                if closed and not show_all:
                    continue
                label = f"{context} : {raw}" if context else raw
                label = re.sub(r"[*_`]", "", label).strip()
                items.append((n + 1, "closed" if closed else "OPEN", label))

            if not items:
                continue
            if not header_shown:
                print(f"\n{'=' * 72}\n{repos[key]}\n{'=' * 72}")
                header_shown = True
            print(f"\n  {f.parent.name if f.parent != repo else f.name}")
            for line, state, label in items:
                if state == "OPEN":
                    open_count += 1
                mark = "->" if state == "OPEN" else "  "
                print(f"   {mark} {state:6} L{line:<4} {label[:100]}")
    return open_count


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course", action="append",
                    help="limit to one course key, repeatable")
    ap.add_argument("--all", action="store_true", help="include closed items")
    args = ap.parse_args()

    root = find_root()
    repos = discover(root)
    if not repos:
        print(f"no course repos with a FEEDBACK.md found under {root}")
        return 0
    unknown = [c for c in (args.course or []) if c not in repos]
    if unknown:
        print(f"unknown course(s) {', '.join(unknown)}. "
              f"Found: {', '.join(sorted(repos))}")
        return 1
    n = scan(root, repos, args.course or sorted(repos), args.all)
    print(f"\n{'=' * 72}")
    if n:
        print(f"{n} open lab issue(s).")
    else:
        print("No open lab issues tagged. Tag actionable notes with TODO(spring).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
