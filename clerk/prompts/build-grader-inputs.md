# Build the grader inputs for a deliverable

Copy this file into the course project (`ITS-3100-Devel`, `ITS-4750-Infrastructure`)
and run it as the last step of rubric development, after the rubric is settled
and the lab is posted to Canvas.

You are producing two files that a separate tool, `Canvas-Tools/clerk`, uses
to grade student lab reports. You are not writing the grader. You are writing
its instrument. Read `Canvas-Tools/clerk/INPUT-SPEC.md` for the normative
format before you start, and follow it exactly.

## What you produce

```text
Canvas-Tools/clerk/cards/<course>-d<NN>.md
Canvas-Tools/clerk/labs/<course>-d<NN>.md
```

For example `cards/3100-d01.md` and `labs/3100-d01.md`.

## Order of work

### 1. Get the Canvas rubric, not a description of it

Pull the live rubric from Canvas for the assignment you just posted. Use
`Canvas-Tools/course-admin/canvas_api.py` or the rubric JSON you posted from
`course-admin/profiles/rubrics/`.

**The Canvas rubric is the authority.** The card mirrors it criterion for
criterion, heading text for description text, points for points. If the card and
Canvas disagree, the card is wrong.

**This is not a formality. The existing grading material contradicts itself.**
In ITS 3100 Deliverable 01, `Grading Guide/Deliverable 01 - Grader Card.md` is
task mapped and sums to 90 across nine sections (10/10/10/10/10/20/5/10/5), while
`Grading Guide/Deliverable 01 - Grading Guide.md` describes five 15 point grader
criteria plus a 15 point Faculty Review. Those are two different instruments
wearing the same name. Resolve that against Canvas before writing anything, and
tell Brandon which one Canvas actually holds.

Task mapped criteria are the better shape and the direction the course is
already moving. Deliverable 04 in ITS 4750 is built that way, and
`course-admin/profiles/rubrics/NEXT-YEAR-RUBRICS.md` says the generic five by
fifteen rubrics in D01 to D03 are a poor fit. If you are building a rubric from
scratch, build it task mapped.

### 2. Copy the handout Objective into every criterion

Each task in the deliverable handout carries an **Objective** line in an
IMPORTANT callout. Copy it verbatim into the criterion's `objective:` field.

That line is the standard, because it is what the student was told to achieve.
Everything else on the card exists to measure it. Lint compares the two and
fails a mismatch, and the judge is shown the objective before the checklist and
told the objective wins.

If a criterion has no matching Objective in the handout, stop and say so. It
means the rubric is grading something the student was never asked for, and the
fix is to the lab, not to the card. This has already happened once: ITS 3100
Deliverable 01 carries a live 5 point row for an Additional Question that does
not appear in the handout.

If a task has no Objective line at all, that is a handout defect too. Report it.

### 3. Harvest evidence bullets from what already exists

In order of trust:

1. **The existing Grader Card**, if there is one, under `Grading Guide/` or
   `Grading/`. Its Full points and Critique lists were written against real
   submissions and are the best material you have.
2. **The deliverable handout**, specifically the per task Objective lines and
   any numbered step that says capture, show, explain, compare, or prove. Every
   one of those is a thing that should appear in the report, so every one is a
   candidate bullet.
3. **The lab README in the student repo** (`ITS-4750-Lab-NN`), which sometimes
   carries steps the handout does not.

Do not invent bullets from general knowledge of the protocol. If a bullet does
not trace to something the student was actually told to do, it is not gradeable,
and it will cost a student points for an instruction they never received.

### 4. Write the Evidence lists

The spec has the full rules. The four that matter most:

- Observable, not inferred. "ping6 to 2606:4700:4700::1111 succeeds", not
  "student demonstrates IPv6 connectivity".
- One fact per bullet. Split anything joined by "and".
- Name the artifact, the command, or the address the judge should look for.
- Prefer bullets that a fluent student who did no work would fail. Specific
  addresses, specific command output, and specific numbers are resistant to
  good writing. "Explained clearly" is not.

Six to eight per criterion.

### 5. Write the Critique lists

The known failure modes for that criterion. Pull from the existing card's
Critique section first. These become the feedback comment on an Acceptable
rating, so write them as things that are wrong, not as advice.

### 6. Build lab.md

Mechanical reduction of the handout: one `## Task N - Title` section per task,
the Objective line, and the numbered steps that produce evidence. Drop setup
prose, tech nugget links, and cleanup steps. Keep the task numbering identical to
the handout, because the card's `tasks:` lists join against these headings.

### 7. Carry the canary across

If the lab README carries a hidden AI use marker, put the exact string in the
card front matter `canary` field, and nowhere else. Do not mention it in any
Evidence or Critique bullet, and do not describe it in prose anywhere in either
file. The grader quarantines on it in code before a prompt exists.

If the lab has no marker, set `canary: null`.

### 8. Lint, then stop

```text
python -m clerk card lint cards/<course>-d<NN>.md
```

Fix what it reports. Then **leave `reviewed_by` and `reviewed` unset** and hand
the card to Brandon.

You do not sign the card. The signature is a human asserting that the instrument
is correct, and the grader will not run without a current one. Tell him what you
had to resolve, especially anything where the existing material contradicted
Canvas or itself, so he knows where to look.

## What good looks like

A card someone can grade from by hand. If a human reading only `card.md` and the
student report could not reach the same rating you would, the card is
underspecified, and the model will not do better than the human would.

## What to tell Brandon when you hand it over

- Which decomposition Canvas actually holds, and whether it matched the existing
  grading material
- Any Evidence bullet you were unsure about, and why
- Any task in the handout that produces no gradeable artifact, since that is
  usually a lab defect worth fixing rather than a grading problem
- Whether the lab carries a canary
