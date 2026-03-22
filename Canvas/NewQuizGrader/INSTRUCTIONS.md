# New Quiz Short Answer Grader — Build Instructions for Claude

## Goal

Build a Python script that pulls all student short answer (and essay) responses from a Canvas New Quizzes assignment and displays them sorted by question, so the instructor can review and score them.

---

## Context & Background

This is a **Canvas New Quizzes** assignment (not Classic Quizzes). New Quizzes runs as an LTI external tool. The grading script must deal with **two separate API surfaces**:

1. **Canvas REST API** (`ohio.instructure.com/api/v1/`) — standard, uses Bearer token, handles submissions/grades
2. **Canvas New Quizzes API** (`ohio.instructure.com/api/quiz/v1/`) — also on the Canvas domain, also accepts the Bearer token ✅

The quiz-engine API (`ohio.quiz-api-pdx-prod.instructure.com`) requires a special LTI JWT and **cannot** be used from a script with the standard Canvas API token.

---

## What We Know Works (Confirmed in Browser)

### 1. Get Quiz Metadata
```
GET /api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}
Authorization: Bearer {ACCESS_TOKEN}
```
Returns: `id`, `title`, `points_possible`, `published`, `quiz_settings`, etc.

### 2. Get Quiz Question Items (Structure)
```
GET /api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/items
Authorization: Bearer {ACCESS_TOKEN}
```
Returns: Array of question items including `id`, `position`, `points_possible`, `entry_type`, and nested `entry` with `item_body` (HTML question text), `interaction_type_slug` (e.g. `rich-fill-blank`, `matching`, `true-false`, `multi-answer`).

### 3. Get All Student Submissions (Canvas REST)
```
GET /api/v1/courses/{course_id}/assignments/{assignment_id}/submissions
Authorization: Bearer {ACCESS_TOKEN}
```
Returns per-student: `user_id`, `score`, `workflow_state` (`pending_review` = needs manual grading), `submitted_at`, and crucially a `url` field that contains:
```
https://ohio.instructure.com/courses/.../external_tools/retrieve?assignment_id=...&url=https%3A%2F%2Fohio.quiz-lti-pdx-prod.instructure.com%2Flti%2Flaunch%3Fparticipant_session_id%3D{PARTICIPANT_SESSION_ID}%26quiz_session_id%3D{QUIZ_SESSION_ID}
```
Parse `participant_session_id` and `quiz_session_id` from this URL — you'll need them.

### 4. Get Student User Info
```
GET /api/v1/courses/{course_id}/users?enrollment_type[]=student
Authorization: Bearer {ACCESS_TOKEN}
```
Returns: `id`, `name`, `email`, `login_id` — join on `user_id` from submissions.

### 5. Write a Grade Back to Canvas
```
PUT /api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}
Authorization: Bearer {ACCESS_TOKEN}
Content-Type: application/json

{"submission": {"posted_grade": 87}}
```

---

## The Auth Challenge for Per-Question Responses

The **quiz-engine API** (`ohio.quiz-api-pdx-prod.instructure.com`) which holds per-question student responses requires an LTI JWT, not the Canvas Bearer token. Direct calls to it return 401.

### What to Try (in order)

**Option A — Canvas quiz/v1 submission endpoint (needs discovery)**

The `/api/quiz/v1/` path on the Canvas domain accepted auth for quiz and items. Try these endpoints to see if any return student response data:
```
GET /api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/submission_users
GET /api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/submissions
GET /api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/item_results
GET /api/quiz/v1/courses/{course_id}/quizzes/{assignment_id}/results
```
Log the HTTP status for each and inspect any 200 responses.

**Option B — quiz-api with Canvas token as-is**

Try sending the Canvas Bearer token to the quiz-api domain directly anyway:
```
GET https://ohio.quiz-api-pdx-prod.instructure.com/api/quiz_sessions/{quiz_session_id}/results
Authorization: Bearer {ACCESS_TOKEN}
```
It returned 401 in browser testing but may behave differently from a server-side script (no CORS restrictions).

**Option C — SpeedGrader submissions endpoint**

Canvas SpeedGrader successfully calls:
```
GET https://ohio.quiz-api-pdx-prod.instructure.com/api/quiz_sessions/{quiz_session_id}/results/{result_id}/session_item_results
```
The `result_id` (e.g. `342746`) was observed in network traffic when SpeedGrader loaded. Try to find a Canvas API endpoint that returns result_ids, or iterate through submissions and try to derive it.

---

## Known IDs (Dev Course — for testing)

```
CANVAS_URL    = https://ohio.instructure.com
COURSE_ID     = 11149       # Dev - ITS 2140
ASSIGNMENT_ID = 728777      # 1st Exam (New Quiz)
QUIZ_SESSION_ID = 300835    # Observed from SpeedGrader network traffic
TEST_STUDENT_ID = 153382
TEST_PARTICIPANT_SESSION_ID = 299222
TEST_RESULT_ID  = 342746
```

Production course:
```
COURSE_ID     = 65879
ASSIGNMENT_ID = 687694
```

---

## Exam Structure (for context)

| Questions | Type | Source | Points |
|-----------|------|---------|--------|
| 1–5 | Matching | Direct | 18 pts |
| 6–12 | True/False | Item Bank: "Exam 1 - T-F" (7 random) | 7 pts |
| 13–22 | Multiple Choice | Item Bank: "Exam 1 - Multiple Choice" (10 random) | 30 pts |
| 23–27 | Short Answer | Item Bank: "Exam 1 - Short Answer" (5 random) | 25 pts |
| 28 | Essay | Direct — "Technical Writing" | 20 pts |

**Only Q23–28 need manual grading.** Matching, T/F, and MC are auto-graded by Canvas.

The `workflow_state` of `pending_review` on a submission means it has ungraded short answer/essay questions.

---

## Script Requirements

### Inputs (from `.env`)
```
ACCESS_TOKEN=...
CANVAS_URL=https://ohio.instructure.com
COURSE_ID=11149
ASSIGNMENT_ID=728777
```

### Output

A console display (or CSV) grouped by question, showing for each short answer / essay question:

```
========================================
QUESTION 23 — "Explain what a protocol is..." (5 pts)
========================================
  [Student: Alice Smith]
  "Protocols are rules for communication..."

  [Student: Bob Jones]
  "A protocol is a set of standards..."

========================================
QUESTION 28 — Essay: Technical Writing (20 pts)
========================================
  [Student: Alice Smith]
  "System diagrams document the internal construction..."
```

### Architecture

1. Load `.env` config
2. `GET /api/quiz/v1/courses/{id}/quizzes/{assignment_id}/items` — build a dict of `{item_id: question_text}` filtered to only short answer and essay types
3. `GET /api/v1/courses/{id}/assignments/{assignment_id}/submissions` — get all submissions, parse `quiz_session_id` and `participant_session_id` from each URL
4. `GET /api/v1/courses/{id}/users?enrollment_type[]=student` — build `{user_id: name}` lookup
5. For each submitted student — retrieve their per-question responses (use best available method from the "Auth Challenge" section above)
6. Group responses by question position, print sorted output
7. Optionally: prompt for a score per student per question, then POST grades back

### File Location

Save the script as:
```
Canvas/NewQuizGrader/new-quiz-grader.py
```

Reuse the existing `.env` pattern from `Canvas/.env` (already has `ACCESS_TOKEN` and `CANVAS_URL`).

---

## Existing Patterns to Follow

See `Canvas/ABET/ABET-graphql-query-paged.py` for:
- `.env` loading pattern
- `requests` usage with Bearer auth
- Pagination with `pageInfo` / cursor

The existing `.env` file is at `Canvas/.env` — the new script should load from there or accept a path argument.

---

## Notes

- The test student submission (`student_id=153382`) has junk/random answers — good for testing structure but scores will be nonsense.
- `workflow_state: pending_review` means there are ungraded questions.
- `workflow_state: graded` means all questions have been scored.
- When writing grades back, use the Canvas REST API submission update — do NOT try to write individual question scores through the quiz engine API.
- Be careful not to commit the `.env` file (check `.gitignore`).
