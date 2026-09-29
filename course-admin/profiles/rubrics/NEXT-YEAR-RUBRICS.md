# Next year: rebuild the D01, D02, D03 Grader rubrics (B versions)

Brandon, 2026-09-13.

The Fall 2026 Grader rubrics for Deliverables 01, 02, and 03 use five generic
dimensions (Deployment Evidence, Debugging Process, Protocol Nuances, Additional
Design, Report Standards) at 15 points each. In practice they are nearly useless
for grading: the lines do not line up with the tasks students actually did, so
graders have to translate.

D04 got it right: task-mapped criteria, one per task group, points weighted by
what matters, Complete note written from the task's Objective. Do that for
D01-D03 next year.

What to do:
- Build "Deliverable 0N - Grader B" rubrics for 01, 02, 03 in
  `Canvas-Tools/course-admin/profiles/rubrics/` using `d04-grader.json` as the model
- One criterion per task or task group, in task order
- Points weighted toward the tasks that carry the learning objective
- Complete rating = one sentence from the task's Objective (the IMPORTANT block in the lab README)
- Any bonus as an extra criterion above the assignment points
- Re-PUT points_possible after the rubric association (Canvas bumps it to the rubric total)
- Rewrite the Grading/ cards to match

Do not retrofit Fall 2026. D01 was made to work by hand this term.
