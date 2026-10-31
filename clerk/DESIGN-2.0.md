# Clerk 2.0: a hosted grading assistant

Status: design, not built. Written 2026-10-02 from what Clerk 1.0 taught while
grading four deliverables across two courses.

1.0 is a command line tool on one workstation. 2.0 is the same grading engine as
a service on the AI app host, so more than one faculty member can use it without
anyone installing Python.

## The boundary

**Clerk produces review documents. It does nothing else.**

It does not post grades, does not email students, does not report misconduct,
does not decide anything. A faculty member reads what it produces and grades in
Canvas themselves.

This is what makes the rest defensible: Clerk can be wrong, and being wrong then
costs a reader ten minutes rather than costing a student a grade. Every later
feature request that crosses this line has to argue against it explicitly rather
than arriving as an obvious convenience.

The AI use canary is the model. It grades the submission like any other, says
nothing in the feedback, and hands the instructor the name. No automated
accusation and no automated penalty, ever.

## Shape

**The grading engine stays a library.** Card parsing, the rating rule, the
verbatim check and the machine checks stay importable and stay driveable from a
terminal. The web app is a shell that queues jobs and serves results.

The moment grading logic lives inside a request handler it stops being testable,
and the ability to re-run a deliverable from a shell when the web layer is broken
is worth more than any convenience the web layer adds.

**Results stay as files.** Markdown review sheets, as now. No grading UI: the
sheets diff, they open in any editor, and a web grading interface would compete
with SpeedGrader for a large build and little gain. The web app does submit a
job, watch it, fetch the results.

## Cards

### Two levels

A course card and a deliverable card, the second inheriting from the first.

The split is already visible in 1.0. Report Standards is near identical across
all three ITS 3100 deliverables, and `image_defaults` is a property of the
cohort rather than of any one lab. Re-minting a gHost image should edit one
course card, not twelve deliverable cards.

| Level       | Holds                                                               |
| ----------- | ------------------------------------------------------------------- |
| Course      | formatting criteria, image defaults, canary convention, accepted submission formats |
| Deliverable | task criteria, objectives, evidence and critique bullets, rubric id |

### Authoring

A Claude skill reads the lab, the QA material and the Canvas rubric, and drafts
a deliverable card.

**The skill must emit a draft that fails lint until a human fixes it.** It will
otherwise reproduce the defects 1.0 found, because they all come from reading a
procedure and turning it into a checklist, which is exactly what the skill does:

- process steps graded as evidence (3100 D02: "Server terminated cleanly",
  missed by 28 of 29, because pressing Ctrl-C leaves nothing to paste)
- compound bullets demanding two artifacts at once
- one requirement split across several criteria, multiplying one miss into three

`card lint` becomes the contract between the skill and Clerk, and every rule
learned the hard way becomes a lint rule the draft is measured against.

**The signature gate survives unchanged.** A card does not grade until a human
has signed it, and editing it invalidates the signature. The evidence for this
is blunt: in 1.0, every card written by the instructor agreed with the
instructor's own grades within a few points, and every card written by Claude
disagreed by twenty to thirty.

## Credentials

**Canvas access is read only, and Clerk enforces that, not Canvas.**

A Canvas personal access token is unscoped: it carries the user's full
permissions, including writing grades. There is no read only variant. So the
guarantee has to be a verb allowlist in Clerk's Canvas client, the same shape as
the inference host allowlist already in `engine.py`: GET only, refuse PUT, POST
and DELETE at the client, with a test that proves it.

If enforcement on Canvas's side is wanted instead, that is an OAuth developer
key with read scopes rather than a personal token. More setup, real enforcement.

**Tokens are held for the lifetime of a job and discarded.** Never at rest. Doug's
DARS AI is the precedent: DARS text never touches disk, core dumps disabled,
swap disabled. The same discipline applies more strongly here, because a Canvas
token is reusable where a DARS report is not.

## Data retention

On a shared host, student work accumulates across faculty and terms. A retention
policy belongs in the design, not added after it has users.

When a faculty member marks a run accepted:

| Artifact                | Keep | Why                                                     |
| ----------------------- | ---- | ------------------------------------------------------- |
| Submissions             | no   | Canvas is the system of record; this is the bulk, about 20 MB per 29 students |
| Extracted images        | no   | regenerable, and large                                   |
| **Dossiers**            | yes  | what the evidence quotes point into. A dispute in week 12 needs "here is the sentence from your report" to be checkable. All 29 D02 dossiers are under 1 MB |
| Verdicts, review sheets | yes  | the output, and small                                    |

Per faculty isolation from the start. One instructor cannot read another's runs.

## Queue

**Model residency is the constraint, not CPU.** spark-01 runs
`OLLAMA_MAX_LOADED_MODELS=1`, so two faculty wanting different judge models
would thrash a 65 GB model in and out. The queue groups jobs by model and drains
them together rather than running FIFO across models.

**There is no preemption and there will not be.** A call in flight is about 167
seconds on the 120B and cannot be cancelled through Open WebUI. So admin control
over batching means time windows, per faculty quotas, and draining or stopping
*between students*, not interrupting work in progress. Jobs are resumable, so
stopping between students costs at most one student's criteria.

Which models are offered, and on which box, is an operational decision that sits
with whoever runs the hardware.

## Variance, shown rather than claimed

Grading runs one request in flight because batching is not deterministic:
measured on the same report three times, two slots gave 85, 74, 84 and one slot
gave 81, 83, 83 with two passes identical.

Single slot is near deterministic. It is not guaranteed, and the honest thing is
to say so and let the faculty member measure it.

**`--passes N`**: grade each report N times, report the modal rating and how
often each criterion moved.

> Graded 3 times. 7 of 9 criteria identical across all passes.
> Task 4 varied between Acceptable and Complete.

This turns a hidden flaw into a number on the page. It is also a cheap
regression test whenever a model is updated underneath the service.

## Failure must be loud

Every serious failure in 1.0 was silent:

- a non-zero exit from a succeeded stage, swallowed by a shell `&&`, so three
  stages never ran and nobody noticed for twelve hours
- a PowerShell stderr trap that killed a scheduled run with no error in the log
- OCR returning empty for two days because the binary was not on PATH, while the
  module imported fine

A job that half finishes must surface as failed, never as complete with fewer
results. The stage completeness check in `pipeline.py` is the start of this: a
stage is judged by whether it produced what the next stage needs, not by its
exit code.

## Deliberately deferred

To reconsider after 2.0 ships, not before:

- **Reproducibility of a past run.** Not required today. Would mean pinning
  model versions and archiving dossiers against them. Much easier to design in
  than to add, so revisit before the data retention policy hardens.
- **A generalised course card as a first class object** rather than a file
  convention.
- **Writing anything back to Canvas.** Out of scope by the boundary above, and
  should stay out until calibration against hand grades is boring.
