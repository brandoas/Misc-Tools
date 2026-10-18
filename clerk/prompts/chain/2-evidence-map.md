# Stage 2: Build the Evidence Map

Run in the QA context for this lab, after the reference build passes, or as far
as it passes. Output is one file:

- ITS 4750: `ITS-4750-Infrastructure/Grading/QA/4750-dNN-evidence.md`
- ITS 3100: `ITS-3100-Devel/Grading/QA/3100-dNN-evidence.md`

You are writing for a different session, the Lab NN Manager, which will turn
this into rubric criteria and Evidence bullets. It will not read your code, your
playbooks, or `decisions.md`. Everything it needs to know about what correct work
looks like has to be in this file. Do not write rubric text or bullets yourself.
Describe the evidence; the Manager decides what is graded.

## Read first

- The handout, every task and every numbered step.
- Everything the rig has recorded: `decisions.md`, `answer-key/`, `OBSERVE.md`,
  `FEEDBACK.md`, the proofs in `run.py` or `qa-labNN.sh`, and any lab memory.
- The site allocation (`answer-key/site-029.yml` or the course's equivalent),
  because it decides which numbers are fixed and which vary per student.

## One section per handout task

Use the handout's task numbers and titles exactly: `## Task N - Title`.

For each task:

**Objective.** Copied verbatim from the handout. If there is none, say so.

**Steps that produce evidence.** The step numbers whose output belongs in a
report, and what each one produces.

**Reference output.** Real output from the reference build, trimmed to the lines
that prove the Objective. Text, fenced, never a screenshot. Say which device and
which command produced it.

**Invariant.** What will be identical in every correct student report: command
names, field names, protocol states (`Full`, `REACHABLE`, `dadfailed`),
message types (RS, RA, NS, NA), counts, flags. These become exact string bullets.

**Varies per student, and the rule.** Every value that differs by gHost,
`vm_num`, allocation or lease, with the rule a correct value obeys instead of the
value: "an address inside the student's delegated /56", "IPv4 gateway is the
last usable", "pool of 200 between the statics and the gateway", "a delegated
prefix, which moves between runs". Never give the reference value as the answer.

**Negative control.** The before state, the teardown, or the blocked path that
proves the feature is carrying the traffic, and the exact command that produces
it. Say if a rerun cannot reproduce it.

**Traps.** From the rig's own history:
- Looks wrong, is correct. A grader would deduct for it and should not.
- Looks right, is wrong. A report could show it and still have failed.
- Environment facts a student cannot control (names the GUI rewrites, prefixes
  that move, first packet loss after idle).

**Not provable here.** Anything the Objective asks for that the reference build
could not show, and why. This is a handout or environment defect, not a grading
problem; say which.

## After the tasks

A short list of course wide format facts the rig established for this lab:
which outputs are naturally text, which are naturally images (diagrams,
browser windows), and anything a student would be tempted to screenshot that
must be text.

Keep it short. A Manager should be able to read the whole file in five minutes.
Real output beats description every time.
