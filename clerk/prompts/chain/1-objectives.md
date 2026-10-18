# Stage 1: Lab Task Objectives

Run in the Lab NN Manager session while the lab is being written or revised,
before the rubric exists. If the lab is already posted this term, do the review
and write the findings as next year notes only. Do not edit a live handout.

## Why this matters

The Objective line is the root of everything graded. The Clerk judge is shown
it first and told it wins over the checklist. An Objective that names no
observable outcome leaves the rubric, the card and the judge with nothing to
measure, and every one of them fills the gap with guesswork.

## Read first

- The handout for this lab, every task.
- The course's authoring rules: `LAB-AUTHORING.md` (4750) or the house style in
  `CLAUDE.md` (3100). Objectives follow them: no rationale, no "because", no
  em dashes.
- The QA rig's status for this lab (`qa/decisions.md` or `FEEDBACK.md`), only to
  learn which tasks the reference build can and cannot prove.

## What a good Objective is

One sentence. A verb the student performs, the thing it is performed on, and
the proof that it worked.

- Good: "Configure every device in the network with Ansible, and prove the lab
  path works end to end."
- Good: "Prove that SLAAC, DHCPv6, and IPv6 Routing properly function."
- Weak: "Interact with the GNS3 API directly." Nothing to prove.
- Weak: "Practice running Ansible playbooks and reading their output at
  increasing levels of verbosity." Practice is not an outcome.

Tests for each one:

1. **Provable.** Could the QA rig check it, or could a report show it with
   command output, a capture, or a before and after? If neither, rewrite it.
2. **Failable.** Could a student who did the task badly fail it? If anything
   that happened would satisfy it, it is too loose.
3. **Asked for.** Every outcome named in the Objective has a numbered step that
   tells the student to produce it, and at least one step says capture, save,
   record, show, explain, or compare. A task with no such step produces no
   gradeable artifact.
4. **Scoped.** One Objective per task. If it needs "and" across two unrelated
   outcomes, the task is probably two tasks, or two rubric bullets at least.
5. **Negative control where it fits.** Where the lab builds a path, a tunnel, a
   rule or a route, the proof is stronger if the Objective implies the before
   state: "prove the tunnel carries the traffic" rather than "show the tunnel
   is up".

## What you produce

A table, then proposed wording. Nothing applied unless Brandon says so.

| Task | Current Objective | Provable | Failable | Capture step(s) | Problem |
|---|---|---|---|---|---|

Then, for every row with a problem, the replacement line written to paste, and
any capture step the task needs and does not have, written in the course's step
form. Flag any task with no Objective at all, and any task whose Objective the QA
rig showed cannot be met in this environment.

Do not explain the pedagogy in the Objective. If something needs explaining,
offer it as lecture or pre-lab material.
