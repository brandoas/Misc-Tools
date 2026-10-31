# Stage 3: Build the Canvas rubric

Run in the Lab NN Manager session after the Objectives are settled and the
Evidence Map exists. Output is a rubric JSON in the course repo's
`Grading/Rubric/<course>-dNN-grader.json`, and nothing else. Brandon posts it
with `put-rubric.py` from `Misc-Tools/course-admin`; you do not need that repo. The human grader card and the Clerk card come later, from this.

Model: a task mapped rubric already in this repo's `Grading/Rubric/`:
`4750-d04-grader.json` in ITS 4750, `3100-d01-report.json` in ITS 3100. The
rules are under Shape below.

## Read first

- The handout Objectives for every task.
- The Evidence Map for this lab.
- The model rubric, for shape.
- Any existing rubric for this deliverable, live in Canvas, and any next year
  notes for it. If the lab is already posted with a rubric, stop: this term's
  rubric does not change. Write the proposal as a next year note instead.

## Shape

- **Task mapped.** One criterion per task or task group, in task order. Never
  generic dimensions ("Protocol Nuances", "Debugging Process") that a grader
  has to translate back into tasks.
- **Criterion description** names the task content. **long_description** names
  the tasks it covers: "Tasks 5-7: ...".
- **Complete** long_description is the Objective, or the Objectives of the
  grouped tasks, close to verbatim. That is the sentence the Acceptable comment
  is measured against.
- **Acceptable** is full minus one, "Partial - see comments". **Missing** is 0,
  "Absent or not data backed".
- **Points** weighted toward the tasks that carry the learning objective, not
  spread evenly. Setup and tooling tasks are light. Tasks with a negative
  control or real analysis are heavy.
- **Report Standards** is its own criterion, 5 to 10 points, taken from the task
  criteria rather than added to the total. It is the row the Clerk checks
  mechanically: one file of the right type, terminal output as text in fixed
  width, packet data as text not a Wireshark screenshot, drawn diagrams.
- **Bonus** as an extra criterion above the assignment total. Re-PUT
  points_possible after the association, because Canvas bumps it to the rubric
  total.
- Tasks graded somewhere else (PreLab, Faculty Review) are left off, and the
  card says so.

## Checks before you post

- Every criterion traces to an Objective. A criterion with no Objective behind
  it grades something the student was never asked for. Stop and report it.
- Every task with an Objective lands in some criterion, or is explicitly graded
  elsewhere.
- Every Objective the Evidence Map marked "not provable here" is either out of
  the rubric or flagged to Brandon.
- Points sum to the assignment total, bonus aside.

## Hand back

The JSON, a one line per criterion summary (name, points, tasks), and anything
you had to decide that Brandon should look at, especially weighting.
