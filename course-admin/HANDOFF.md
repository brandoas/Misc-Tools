# Handoff: shared Canvas abilities (any Brandon Saunders course)

Paste this into a course project's instructions or first message. It describes the Canvas tooling built in the ITS 4750 project and the conventions that apply to every course. A short course-specific block follows for ITS 6440.

## Where the tooling lives
- Repo on its099 (Brandon's work machine): `C:\Users\saundeb1\Documents\Git\Canvas-Tools\course-admin\`. Mount from its099, not the home machine.
- Token: repo-root `Canvas-Tools\.env` (`ACCESS_TOKEN = "..."`, `API_URL = "https://ohio.instructure.com/api/graphql"`). Never print or commit it. `canvas_api.py` walks up parent folders to find `.env`.
- Brandon's local Cowork VM has no network. Stage `.env` and the scripts into the cloud workspace and run them there; write results back with the device tools. Delete the cloud copy of `.env` when done.
- Python 3, `requests`, `python-dotenv`.

## What the scripts do
- `init-course.py PROFILE COURSE_ID --term-start YYYY-MM-DD [--only ...] [--apply]`: one pass that applies navigation, course settings, feature flags, and starter items from a profile JSON. Dry run by default; `--apply` executes; run again to confirm zero drift. Existing starter items are matched by title and skipped.
- `dump-course.py COURSE_ID --name "..."`: build a profile from a course that went well.
- `put-rubric.py RUBRIC.json COURSE_ID ASSIGNMENT_ID [--apply]`: create a rubric and attach it to an assignment. One rubric per assignment; refuses to replace.
- `set-navigation.py`, `audit-navigation.py`, `list-courses.py`, `list-modules.py`, `get-syllabus.py`, `put-syllabus.py`: the older single-purpose tools.
- `coursekit.py`: the library. Direct API calls for things the scripts do not cover yet (assignments, modules, New Quizzes) follow the patterns in this session: `ck.get`, `ck._json_post`, `ck._json_put`.

## Conventions that apply to every course
- Never touch grades, submissions, or the People list. Every mutating action is a dry run first; apply only when Brandon says so.
- New Quizzes only. Feature flags `quizzes_next` ("New Quizzes") and `new_quizzes_by_default` (UI label "Disable Classic Quiz Creation") are ON in every Fall 26 course. Create quizzes through `/api/quiz/v1/courses/:id/quizzes` then `/items`, publish through the assignments API. `score_to_keep` is required when multiple attempts are enabled.
- Default due time is per course (4750 = 5:00 PM, 3100 = 11:59 PM). Check `/courses/:id/settings` before assuming.
- Gradebook policy (every course): late policy missing = 0 percent grade (100 deduction), late = 100 percent deduction per day, no minimum. Intentional: IT deadlines (outages, updates) are dead level, so any delay scores 0. Do not soften this or suggest grace periods; the Faculty override and excused status are the escape hatches.
  Also: allow_final_grade_override true; view settings hide unpublished assignments, split student names, hide assignment group totals (per user, via PUT gradebook_settings). Arrange By due date newest first and status icons are manual View-menu clicks; the API cannot set them.
- Navigation: shared always-on set is Home, Syllabus, Modules, Assignments, Quizzes, Grades, People, Settings, Secure Exam Proctor; roughly 20 publisher LTIs always off; Accessibility tab is institution-pinned. Capture a course's nav with `set-navigation.py --dump`.
- Rubrics: sparse and student-facing. Criterion title plus one short phrase (students keep the details themselves). Ratings carry the descriptions: Complete "Meets the objective with clear, well formatted evidence" (full points), Acceptable "Partial - see comments" (full minus 1), Missing "Absent or not data backed" (0). Detail that would let an LLM produce a perfect submission stays in instructor-only files, never in Canvas. Rubric JSONs live in `profiles/rubrics/`.
- Modules: one module per deliverable or unit, an ExternalUrl item to the GitHub repo at indent 0, assignments indented under it.
- Writing style for Brandon: no em dashes or en dashes; terse; ADA tables (caption plus th scope) in any HTML.

## Course IDs
- 82426 ITS 4750 Fall 26, 54157 4750 Fall 25, 29597 Devel 4/5750
- 81149 ITS 3100 Fall 26, 54643 3100 Fall 25, 40822 Devel 3100
- 79617 ITS 6440 Fall 26, 48211 6440 Fall 25, 29598 Devel ITS 6440

## ITS 6440 Fall 26 (79617) specifics
- Strategic Issues in ITS Technology and Policy, graduate, Fall 26, unpublished as of 2026-08-21.
- Done: New Quizzes flags ON (2026-08-21). Nothing else has been touched.
- Not done: default due time (decide the 6440 convention, then set `default_due_time`), navigation reconcile (`set-navigation.py --dump 48211` to build a 6440 profile, dry run against 79617), `profiles/6440.json` (start with `dump-course.py 48211 --name "ITS 6440"` and prune), syllabus check (`get-syllabus.py 48211` vs `79617`), modules.
- 6440 has no GitHub labs, so the GitHub ID starter quiz and the ExternalUrl module pattern do not apply. Drop `starter_items` from the 6440 profile unless Brandon names one.
- Fall 26 calendar: classes begin Mon Aug 24, Labor Day Sep 7, Fall Break Fri Oct 2, Veterans Day Wed Nov 11, Thanksgiving Nov 25 to 29, last day of classes Fri Dec 4, exams Dec 7 to 12.

## NEXT YEAR: D01-D03 Grader rubrics need B versions (2026-09-13)

The five-generic-dimension rubrics on Deliverables 01, 02, 03 are nearly useless
for grading. Build task-mapped B versions like `ITS-4750-Infrastructure/Grading/Rubric/4750-d04-grader.json`
before Fall 2027. Full note: `ITS-4750-Infrastructure/NEXT-YEAR-RUBRICS.md`.
