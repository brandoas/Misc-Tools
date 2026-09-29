# clerk

Rubric driven first pass grading of ITS 3100 and ITS 4750 lab reports, on Ohio
ECT local inference. It proposes ratings and evidence. A human decides.

It does not post to Canvas. It does not write grades anywhere. Every output is a
Markdown file you read.

## What it is for

A lab report is four to eight pages of command output, packet captures and
analysis, graded against a rubric of ten or so criteria, for two courses and
roughly twenty four deliverables a semester. The judgement calls are real, but
most of the work is looking for whether a specific piece of evidence is on the
page. That part is mechanical, and this does it, then hands you a sheet that
says what it found and where.

## Design rules

**Every stage reads files and writes files.** Nothing is held between stages.
Any stage can be run alone, rerun after a hand edit, or skipped entirely. You
could operate this by hand with a text editor if you wanted to, and on the day
something goes wrong you will want to.

**The model finds evidence. Code decides the rating.** The model reports which
checklist items it can support with a verbatim quote from the report. A rule in
[judge.py](clerk/judge.py) turns those findings into Complete, Acceptable or
Missing. Two students with the same findings get the same rating regardless of
how well either of them writes.

**Every quote is checked against the report.** A quote the model produced that
is not actually in the student's report voids that finding and flags the whole
criterion. That check is what makes a rating answerable when a student
challenges it: the answer is a list of quotes from their own submission.

**One model, one host, no fallback.** Student work only goes to ai-01 or
spark-01, enforced in [engine.py](clerk/engine.py). There is no provider
chain, unlike the other apps on those boxes, because a grade has to be
reproducible and because this is student work.

**Both submission formats are read natively, and never converted.** ITS 3100
Deliverable 01 asks for a PDF, ITS 4750 asks for a .docx from Lab 2 on, and the
Fall 2026 D01 pile is 21 .docx against 11 .pdf. The .docx reader uses real font
metadata from the runs and their style chain; the PDF reader uses font names per
character. Converting a .docx to PDF first would discard the better source,
inherit the harder problem, and reflow the fixed width blocks that evidence
quotes are checked against. Do not add a conversion step.

**Canaries never reach a model.** A submission carrying the AI use marker is
quarantined in code before a prompt exists, and the marker string never enters a
prompt, a verdict or a comment.

## Setup

```
pip install -r requirements.txt
cp .env.example .env
```

Put an ai-01 API key in `.env` as `OHIO_API_KEY`. Mint it in Open WebUI at
https://ai-01.its.ohio.edu under Account settings. `SPARK_API_KEY` is the same
for spark-01, once there is an account there.

Tesseract is optional and improves the image stage. Without it the vision model
still runs.

## Running it

Start here. It checks the key, the host, the model, and whether structured
output survives the Open WebUI gateway, and every failure prints the fix:

```
clerk doctor
clerk doctor --host spark
```

```
clerk card lint cards/3100-d01.md --lab labs/3100-d01.md
clerk extract    runs/3100-d01
clerk vision     runs/3100-d01
clerk assemble   runs/3100-d01
clerk judge      runs/3100-d01
clerk report     runs/3100-d01
```

Every command takes `--force` to redo work it has already done. `judge` takes
`--student NAME` to redo one, and `--host spark` to use the bigger model.

A run directory:

```
runs/3100-d01/
  card.md                  reviewed grader card      you supply
  lab.md                   task context              you supply
  submissions/*.docx       student work, either format, one file per student
  submissions/*.pdf
  extract/*.md             text, monospace fenced, [IMAGE-NN] placeholders
  extract/<student>/*.png  the images themselves
  vision/*.json            OCR and vision model transcriptions   editable
  dossier/*.md             extract plus vision, what the judge reads   editable
  verdicts/*.json          structured ratings
  review/<student>.md      the sheet you grade from
  review/_cohort.md        the class report
  quarantine.json          canary hits, not graded
```

## The two inputs

`card.md` and `lab.md` are the only course specific things here.
[INPUT-SPEC.md](INPUT-SPEC.md) is the normative format.
[prompts/build-grader-inputs.md](prompts/build-grader-inputs.md) is the
instruction set for the rubric development context that produces them, and lives
in each course repo.

**A card must be signed before it can grade anything.** `reviewed_by` and
`reviewed` in the front matter, and `reviewed` has to be newer than the file's
own mtime. Edit the card, the signature goes stale, the tool stops. The grading
guides these cards derive from were largely machine drafted and carry real
errors, so the gate is the point rather than ceremony.

## The cohort report

`review/_cohort.md` is the output worth reading first.

- **Where the class landed**: rating distribution per criterion. A criterion
  that came back Missing for 40 percent or more of the class is a lab or a
  lecture defect, not twenty student failures, and it is called out separately.
- **Clear successes**: work marked worth showing a future class, with the
  excerpt, as raw material for teaching examples.
- **Critical misses**: ratings that failed the verbatim check and are not
  usable, criteria that missed Complete by a single bullet (often a badly worded
  bullet rather than short work), and reports that submitted command output as
  screenshots.
- **Quarantined**: names only.

## Fixtures and calibration

There is no archive of graded reports to calibrate against, so ground truth is
built:

```
python fixtures/make_fixtures.py
clerk extract  runs/3100-d01-fixtures
clerk assemble runs/3100-d01-fixtures
clerk judge    runs/3100-d01-fixtures --unsigned
clerk calibrate runs/3100-d01-fixtures
```

Five reports written to satisfy or fail specific Evidence bullets, with
`expected.json` recording the rating that should follow. `calibrate` scores the
run against it.

The fixtures are `strong` (Complete throughout), `thin` (everything present,
nothing analysed), `partial` (planted gaps taken from the card's Critique
bullets), `screenshots` (correct content pasted as images) and `missing` (two
tasks absent).

`screenshots` is the measurement of what the vision stage is worth. Judge it
once without `vision` and once with, and the difference is the answer.

**What the fixtures do not tell you.** They are machine written, so they are
cleaner and better organised than real student work. They test the card, the
plumbing and the rating rule. The first real deliverable is still an iteration.

## Choosing the host

`--host ai01` runs `gpt-oss:20b` on the A10. `--host spark` runs `gpt-oss:120b`
on the DGX Spark. Wall clock for a class sized batch is close to the same on
both: the 120b generates slower but the box gives it four parallel slots against
ai-01's two, and grading is prefill heavy. So the choice is quality, not speed.
Run `calibrate` against both and pick with a number.

## Tests

```
python -m pytest tests -q
```

Offline. Nothing calls a model, nothing reads a real submission. They cover the
rating rule, the verbatim check, the card review gate and canary matching, which
are the parts that decide a grade without a model in the loop.
