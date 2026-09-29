"""Clerk: assembles the evidence, checks every citation, hands it to the judge.

Named for what it does and, more to the point, for what it does not. A clerk
prepares the case file and verifies that each quotation is really in the record.
It does not decide the case. Every rating this produces is a proposal supported
by verbatim quotes from the student's own report, for a human to accept, revise
or throw out.

The previous name, labgrader, claimed the one thing the tool deliberately
refuses to do.
"""

import os
from pathlib import Path

__version__ = "0.1.0"


def _find_env() -> None:
    """Load every .env from here up to the drive root, nearest wins.

    course-admin's canvas_api.py stops at the first .env it finds. That is fine
    when there is one and a trap when there are two: an empty clerk/.env
    shadows a filled Canvas-Tools/.env completely, and the symptom is a key
    sitting plainly in a file the tool insists is not set.

    Reading all of them nearest first removes the shadowing, so the Canvas token
    can live in the repo root .env beside the inference keys, or the two can
    live apart, and either layout works.

    An empty assignment does not count as set. `OHIO_API_KEY=` is exactly what a
    freshly copied .env.example looks like, and treating that as a value would
    reintroduce the same shadowing through the back door.

    A real environment variable always wins over any file, so a one off
    `OHIO_API_KEY=... python -m clerk ...` still overrides.
    """
    from dotenv import dotenv_values

    d = Path(__file__).resolve().parent
    seen: list[Path] = []
    while True:
        candidate = d / ".env"
        if candidate.is_file():
            seen.append(candidate)
        if d.parent == d:
            break
        d = d.parent

    for path in seen:                       # nearest first
        for key, value in dotenv_values(path).items():
            if value and value.strip() and not os.environ.get(key, "").strip():
                os.environ[key] = value.strip()

    if os.environ.get("LABGRADER_DEBUG_ENV"):
        for p in seen:
            filled = [k for k, v in dotenv_values(p).items() if v and v.strip()]
            print(f"env {p}: {', '.join(filled) if filled else '(no values)'}")


# Loaded at package import, not in __main__, so importing the library directly
# (a probe script, a notebook, a test) gets the same credentials the CLI does.
_find_env()
