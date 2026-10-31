"""Run every stage for one deliverable, in order, unattended.

This exists because chaining the stages with shell `&&` is not safe. On
2026-09-27 the vision stage completed all 29 reports and then exited non zero on
a Windows asyncio teardown error, so `&&` stopped the chain and assemble, judge,
report and notes silently never ran. Twelve hours were lost to a traceback that
looked cosmetic.

So the sequence lives here instead, where a stage's outcome is judged by whether
it produced what the next stage needs, not by a process exit code. A failure
stops the run, says which stage and why, and leaves everything already done in
place, because every stage is resumable.

    python -m clerk pipeline runs/3100-d03 --host spark
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import time
from pathlib import Path

#: Stage, the argv to run it, and what it must leave behind to count as done.
#: `produces` is checked against the number of submissions, so a stage that
#: half finished is caught here rather than three stages later.
STAGES = [
    ("fetch", lambda a: ["fetch", a.run, "--course", a.course, "--assignment", a.assignment],
     None),
    ("extract", lambda a: ["extract", a.run], "extract"),
    ("vision", lambda a: ["vision", a.run, "--host", a.vision_host], "vision"),
    ("assemble", lambda a: ["assemble", a.run], "dossier"),
    ("judge", lambda a: ["judge", a.run, "--host", a.host], "verdicts"),
    ("report", lambda a: ["report", a.run], "review"),
    ("notes", lambda a: ["notes", a.run], None),
]


def _count(run, folder: str, suffixes: tuple[str, ...]) -> int:
    """Count a stage's outputs. `run` is a Run, whose path is run.path."""
    d = (run.path if hasattr(run, "path") else Path(run)) / folder
    if not d.is_dir():
        return 0
    return len([f for f in d.iterdir() if f.suffix in suffixes and not f.name.startswith("_")])


def cmd_pipeline(args) -> int:
    from .__main__ import Run, main as cli

    run = Run(args.run, create=True)
    lock = run.path / ".pipeline.lock"
    if lock.is_file() and not args.force:
        age = (time.time() - lock.stat().st_mtime) / 3600
        print(f"a pipeline is already running on {run.path.name} "
              f"(lock {age:.1f} h old). Use --force to override.")
        return 1
    lock.write_text(_dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8")

    started = time.monotonic()
    print(f"=== {run.path.name} starting {_dt.datetime.now():%Y-%m-%d %H:%M} ===",
          flush=True)
    failed = None
    try:
        for name, argv, produces in STAGES:
            if name == "fetch" and not (args.course and args.assignment):
                print(f"[{name}] skipped, no --course/--assignment given", flush=True)
                continue
            if name == "vision" and args.no_vision:
                print(f"[{name}] skipped by request", flush=True)
                continue

            print(f"--- {name} ---", flush=True)
            try:
                rc = cli(argv(args))
            except SystemExit as e:
                rc = e.code or 0
            except Exception as e:
                failed = f"{name} raised {type(e).__name__}: {e}"
                break

            # The exit code is advisory. What matters is whether the stage left
            # behind what the next one needs; that is what the shell chain got
            # wrong.
            if produces:
                expected = len(run.students())
                got = _count(run, produces, (".json", ".md"))
                # No adjustment for the cohort file: _count already skips
                # names beginning with an underscore. Subtracting for it as
                # well double counted the exclusion and stopped a `report`
                # stage that had in fact written every sheet.
                if expected and got < expected:
                    failed = (f"{name} produced {got} of {expected} expected outputs "
                              f"in {produces}/ (exit code {rc})")
                    break
            elif rc:
                failed = f"{name} exited {rc}"
                break
    finally:
        lock.unlink(missing_ok=True)

    minutes = (time.monotonic() - started) / 60
    if failed:
        print(f"\n=== {run.path.name} STOPPED after {minutes:.1f} min: {failed}",
              flush=True)
        print("Nothing already finished was lost. Rerun the same command to "
              "resume from where it stopped.", flush=True)
        return 1

    print(f"\n=== {run.path.name} complete in {minutes:.1f} min ===", flush=True)
    _summarise(run)
    return 0


def _summarise(run: Path | object) -> None:
    """One line per student, so a morning read of the log tells you enough."""
    path = run.path if hasattr(run, "path") else Path(run)
    roster_file = path / "roster.json"
    roster = json.loads(roster_file.read_text(encoding="utf-8")) if roster_file.is_file() else {}
    rows = []
    for f in sorted((path / "verdicts").glob("*.json")):
        v = json.loads(f.read_text(encoding="utf-8"))
        rows.append((sum(x["awarded"] for x in v),
                     sum(1 for x in v if x["confidence"] == "low"),
                     roster.get(f.stem, {}).get("name", f.stem)))
    if not rows:
        return
    rows.sort(reverse=True)
    total = sum(x["points"] for x in json.loads(
        next((path / "verdicts").glob("*.json")).read_text(encoding="utf-8")))
    print(f"\n{len(rows)} graded, out of {total}:")
    for score, flags, name in rows:
        note = f"  ({flags} flagged)" if flags else ""
        print(f"  {score:3} / {total}  {name}{note}")
    q = path / "quarantine.json"
    if q.is_file():
        hits = json.loads(q.read_text(encoding="utf-8"))
        if hits:
            print(f"\nAI use marker, graded as normal: "
                  f"{', '.join(h['student'] for h in hits)}")
