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

# D06: Task 6 is over-weighted

Brandon, 2026-10-23.

Task 6, take the Pi home and find it again, carries 20 points, the most in the
deliverable, and the handout asks only for the address. One sentence satisfies
it. Task 5 at 15 has a real artifact in the web server log.

Fix one of these for Spring:

- the handout asks for more from home, and the Clerk card gains bullets for it
- the weight moves from Task 6 onto Task 5

Graded as posted for Fall 2026.
