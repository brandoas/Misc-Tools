# Clerk: workflow and the decisions behind it

Clerk assembles the evidence, checks every citation, and hands it to the judge.
It does not decide the case. Every rating is a proposal supported by verbatim
quotes from the student's own report.

## Workflow

Six stages. Each reads files and writes files, so any one can be rerun alone,
hand edited, or skipped.

```
fetch     Canvas to submissions/          read only, never writes a grade
extract   .docx or .pdf to Markdown       fonts, spacing, images, no model
vision    images to text                  OCR first, model only if visual
assemble  extract + vision to dossier     no model, hand editable
judge     dossier + card to verdicts      the only stage that judges
report    verdicts to review sheets       per student, plus a cohort view
notes     verdicts to LAB-NOTES.md        what to fix in the lab next time
```

Two inputs carry everything course specific: `card.md` (criteria, objectives,
evidence bullets) and `lab.md` (task context). No course or deliverable
identifier appears in code.

Measured, 31 reports: fetch 0.6 min, extract 0.3, vision 35.5, judge 155.

## The five decisions that matter

**1. The model finds evidence. Code decides the rating.**
The model reports which evidence bullets it can support with a verbatim quote.
A rule in `judge.py` turns findings into Complete, Acceptable or Missing. Two
students with the same findings get the same rating regardless of how well
either writes.

**2. Every quote is checked against the report.**
A quote that is not in the student's text voids the finding and flags the
criterion as unusable. This is what makes a rating answerable to a student: the
answer is a list of quotes from their own submission. It is also the only guard
against a fluent, confident, wrong verdict.

**3. Local inference only, no fallback chain.**
Student work goes to ai-01 or spark-01 and nowhere else, enforced by a host
allowlist in `engine.py`. Unlike the other apps on those boxes there is no
GitHub Models or Google fallback: student work stays inside the university, and
a grade has to be reproducible, so silently switching models mid run would mean
two students graded by two instruments.

**4. One request in flight, not four.**
`OLLAMA_NUM_PARALLEL` slots are not isolated workers. Concurrent requests are
interleaved into one batched forward pass, and batched floating point reductions
are not associative, so the same prompt gives different logits depending on what
it was batched with. Measured on ai-01, the same report three times:

    two slots   85, 74, 84     eleven point spread
    one slot    81, 83, 83     passes two and three identical

Worse than irreproducible: with concurrency, students batched together are
computed differently from students batched apart, within a single run. The
parallelism is spent to buy that back. A warmup call absorbs the cold first
request.

**5. Model size: the 120B is worth it, the A10 is not the bottleneck.**
Judged 29 real reports on both boxes against hand grades:

| | ai-01, gpt-oss:20b | spark-01, gpt-oss:120b |
|---|---|---|
| Mean absolute gap to the human | 12.5 | **9.5** |
| Per criterion gap | up to 4.0 | all within 1.0 |
| Failures in 303 calls | 31% | **0** |
| Minutes per report | ~3 (healthy) | ~5 |

The 120B is roughly 1.7x slower per report at one slot and agrees markedly
better. For work that assigns grades and runs unattended, that is the right
trade. Note the Spark's four slots would win on wall clock, and decision 4
deliberately gives that up.

## Images

Images are for network diagrams and browser windows. Command output pasted as a
picture is a formatting violation, not evidence, so **its contents are withheld
from the dossier entirely**. Transcribing it would let the judge quote it and
credit a bullet the report was not entitled to satisfy that way, which launders
a violation into a satisfied rating.

Routing is by OCR, before any model call. Text density per megapixel does not
separate a diagram from a terminal (a real diagram measured 1013 chars/MP,
squarely among the terminals); absolute size does:

    network diagrams     163 chars / 6 lines,  346/16,  429/18
    dense screenshots   1895/35, 1922/37, 2221/25, 2376/41

Four images per report, in document order. Beyond that they are recorded as
unread rather than dropped. On one class, 24 of 29 reports were already at four
or fewer, and of the overflow 18 of 30 were terminal screenshots.

This routing, not the faster box, is why vision fell from over five hours to 35
minutes. OCR is also kept for diagrams: it reads labels the vision model misses.

## What is checked in code, not inferred

Facts about the submission rather than its content: file format, whether any
fixed width text exists, whether terminal output was set in a proportional font,
whether a Wireshark screenshot is present. These never reach the model, because
asking it about something it cannot see produces a confident wrong answer. One
deliverable saw 28 of 29 students told "the submission is not a Word document"
about their .docx files.

AI use canaries are handled the same way, before any prompt is built. A model
told not to mention a string will eventually mention it.

## The human gate

A card carries `reviewed_by` and `reviewed`. Clerk refuses to run against a card
whose signature is older than the file. Edit a bullet, the signature goes stale,
the tool stops. The grading guides these cards derive from were largely machine
drafted and carry real errors, including a rubric row worth five points for a
question that appeared in no version of the handout.
