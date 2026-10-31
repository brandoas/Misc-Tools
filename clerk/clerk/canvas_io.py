"""Pull submissions down from Canvas. Read only.

This never writes a grade, a comment, or a rubric assessment. It reads the
assignment, the roster and the submitted files, and nothing else. Posting
results back is deliberately not built.

Files land as submissions/<login_id>.<ext>, because a login id is unique,
filename safe and stable, where a display name is none of those. roster.json
carries the mapping so the review sheets can show real names.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "course-admin"))

#: Extensions the pipeline can read. Anything else is reported and skipped,
#: because a submission silently missing from a batch is the worst outcome here.
READABLE = {".docx", ".docm", ".pdf"}



def _etc(run_path):
    """<run>/etc, created on demand.

    The run root carries the review sheets a human grades from, so everything
    the engine needs but nobody reads lives here: the card, the lab context, the
    roster, the canary list and the stage timings.
    """
    from pathlib import Path as _P
    d = _P(run_path) / "etc"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _api():
    """Import the shared Canvas helper lazily, so nothing else needs a token."""
    try:
        import canvas_api
    except SystemExit as e:
        raise SystemExit(f"Canvas token problem: {e}") from e
    except ImportError as e:
        raise SystemExit(
            "cannot import course-admin/canvas_api.py. clerk expects to live "
            "beside course-admin inside Canvas-Tools."
        ) from e
    return canvas_api


def _similarity(sub: dict) -> dict | None:
    """Pull the originality report off a submission, if there is one.

    Canvas keys `turnitin_data` by attachment, with the similarity score, a
    processing state and a report URL. The state matters: "failure" means the
    report never generated, which is not the same as a low score and must not
    be read as one.
    """
    data = sub.get("turnitin_data") or sub.get("vericite_data") or {}
    best = None
    for key, value in data.items():
        if not isinstance(value, dict) or "similarity_score" in value is None:
            continue
        score = value.get("similarity_score")
        if score is None:
            continue
        row = {"score": score, "state": value.get("state"),
               "report_url": value.get("report_url"), "attachment": key}
        if best is None or score > best["score"]:
            best = row
    return best


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("_") or "unknown"


def cmd_fetch(args) -> int:
    from .__main__ import Run

    api = _api()
    run = Run(args.run, create=True)
    dest = run.dir("submissions")

    course, assignment = args.course, args.assignment
    meta = api.get(f"/api/v1/courses/{course}/assignments/{assignment}")
    print(f"{meta.get('name')} : {meta.get('points_possible')} points, "
          f"due {str(meta.get('due_at'))[:10]}")

    users = api.get_paginated(f"/api/v1/courses/{course}/users",
                              params={"enrollment_type[]": "student", "per_page": 100})
    by_id = {u["id"]: u for u in users}

    subs = api.get_paginated(
        f"/api/v1/courses/{course}/assignments/{assignment}/submissions",
        params={"per_page": 100})

    roster: dict[str, dict] = {}
    downloaded = skipped = 0
    problems: list[str] = []

    for s in subs:
        user = by_id.get(s.get("user_id")) or {}
        login = _safe(user.get("login_id") or str(s.get("user_id")))
        name = user.get("sortable_name") or user.get("name") or login

        if not s.get("submitted_at"):
            problems.append(f"{name} ({login}): nothing submitted")
            continue

        attachments = s.get("attachments") or []
        if not attachments:
            problems.append(f"{name} ({login}): submitted with no file attached")
            continue
        if len(attachments) > 1:
            # Grading one of several files is a decision, not a default.
            names = ", ".join(a.get("filename", "?") for a in attachments)
            problems.append(f"{name} ({login}): {len(attachments)} files ({names}), "
                            f"taking the newest")

        att = sorted(attachments, key=lambda a: a.get("created_at") or "")[-1]
        suffix = Path(att.get("filename", "")).suffix.lower()
        if suffix not in READABLE:
            problems.append(f"{name} ({login}): {att.get('filename')} is not a "
                            f"format clerk reads")
            continue

        target = dest / f"{login}{suffix}"
        if target.exists() and not args.force:
            skipped += 1
        else:
            data = api._session.get(att["url"], timeout=120)
            data.raise_for_status()
            target.write_bytes(data.content)
            downloaded += 1
            print(f"  {login}{suffix}  {len(data.content) / 1024:.0f} KB  {name}")

        roster[login] = {
            "name": name,
            "user_id": s.get("user_id"),
            "submitted_at": s.get("submitted_at"),
            "late": bool(s.get("late")),
            "file": target.name,
            "similarity": _similarity(s),
        }

    (_etc(run.path) / "roster.json").write_text(
        json.dumps(roster, indent=2, sort_keys=True), encoding="utf-8")

    print(f"\n{downloaded} downloaded, {skipped} already present, "
          f"{len(roster)} in roster")
    if problems:
        print(f"\n{len(problems)} submission(s) need your attention:")
        for p in problems:
            print(f"  {p}")
    late = [r for r in roster.values() if r["late"]]
    if late:
        print(f"\n{len(late)} marked late by Canvas. clerk does not apply "
              f"the late policy; that stays in Canvas.")
    return 0
