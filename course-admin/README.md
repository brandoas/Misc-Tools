# course-admin

Course-level Canvas administration scripts, parameterized by course ID so
they work for any class. Successor to the Canvas-Tools folder that lived in
ITS-4750-Infrastructure.

## Setup

1. `pip install requests python-dotenv`
2. Put a token in the repo-root `.env` (see `.env.example`). Either style works:
   `ACCESS_TOKEN = "..."` (legacy) or `CANVAS_API_TOKEN=...`. `canvas_api.py`
   searches this folder, then parent folders, for `.env`.
3. Never commit `.env`.

## Semester start: one pass per course

```
python init-course.py profiles/4750.json COURSE_ID --term-start 2026-08-24          # dry run
python init-course.py profiles/4750.json COURSE_ID --term-start 2026-08-24 --apply  # do it
python init-course.py profiles/4750.json COURSE_ID --term-start 2026-08-24          # verify: zero changes
```

`init-course.py` applies everything in a profile: navigation (visible tabs in
order, everything else hidden), course settings (default due time, final grade
override, etc.), feature flags (New Quizzes, Disable Classic Quiz Creation),
the gradebook (late/missing policy: missing = 0 percent, 100 percent deduction
per day late; view settings: hide unpublished, split student names, hide
group totals), and starter items
(currently New Quizzes with essay questions, due dates relative to
`--term-start`). Anything not in the profile is left alone. Starter items
that already exist (matched by title) are skipped. `--only navigation,features`
limits the pass.

## Profiles

| File | Class | Notes |
|------|-------|-------|
| `profiles/4750.json` | ITS 4750 | default due 5:00 PM; nav from Fall 25; GitHub ID starter quiz |
| `profiles/3100.json` | ITS 3100 | default due 11:59 PM; nav dumped from Fall 25 (54643); GitHub ID starter quiz |
| `profiles/nav-4750-fall25.json` | ITS 4750 | bare nav-only profile, original 2026-08-10 capture |
| `profiles/rubrics/4750-lab01*.json` | ITS 4750 | Deliverable 01 rubrics: Grader (5 rows, 75 pts, rubric 61814), PreLab (10), Faculty (15); live on 82426 |

Build a new profile from a course that went well:

```
python dump-course.py COURSE_ID --name "ITS 2300" > profiles/2300.json
```

then hand-edit (add starter items, prune settings you do not care about).

Not settable via API, so two one-time clicks per course in the gradebook View
menu: Arrange By > Due Date (newest first), and the status icons toggle.

## Other scripts

| Script | Purpose |
|--------|---------|
| `canvas_api.py` | Shared helper: auth, REST GET/PUT with pagination, GraphQL POST |
| `coursekit.py` | Library behind init/dump: plan and apply nav, settings, features, starter items |
| `list-courses.py [filter]` | List course IDs and terms |
| `set-navigation.py` | Nav-only subset of init-course (`--dump` to capture) |
| `audit-navigation.py` | Compare nav across many courses: always on / always off / varies |
| `get-syllabus.py` / `put-syllabus.py` | Download / upload the Syllabus page HTML (put backs up first) |
| `list-modules.py` | List a course's modules and items (`--json` to dump) |
| `put-rubric.py RUBRIC.json COURSE_ID ASSIGNMENT_ID [--apply]` | Create a rubric from JSON and attach it to an assignment (one rubric per assignment; refuses to replace) |

See `HANDOFF.md` for the cross-course conventions to paste into another course's project.

## Scope

These scripts never read or write grades, submissions, or the People list.
Every mutating script is a dry run unless `--apply` is given.

## Course IDs (2026-27)

82426 ITS 4750 Fall 26, 81149 ITS 3100 Fall 26, 79617 ITS 6440 Fall 26.
Templates: 29597 Devel ITS/CS 4/5750, 40822 Devel ITS 3100.
Last year: 54157 4750 F25, 54643 3100 F25.
