# Stage 6: Close the loop after grading

Run in the Clerk context after a real deliverable has been judged and Brandon
has finished grading from the review sheets. The output is a handoff for the
Lab NN Manager. Do not edit a handout, a rubric, or a lab note file yourself.

## Inputs

```text
clerk notes $RUN
```

(`$RUN` is the OneDrive run directory) which writes `LAB-NOTES.md`, plus `review/_cohort.md`, plus Brandon's final
grades where they differ from the proposed ratings.

## Sort every finding to the earliest link that caused it

| Signal | Usually means | Goes to |
|---|---|---|
| One bullet failed by more than 60 percent | handout never asked for it, or the grader cannot see it | Objective or capture step (Stage 1) |
| 40 to 60 percent on one bullet | instruction ambiguous, or easy to do and forget to write down | capture step wording (Stage 1) |
| Brandon overrode the same bullet for many students | bullet wording wrong | card (Stage 4), needs re-signing |
| A criterion Missing for 40 percent or more of the class | lab or lecture defect | Objective, or a lecture note |
| A failure the QA rig never saw | environment differs from the reference build | Evidence Map (Stage 2) |
| Points felt wrong for the effort | weighting | rubric, next year (Stage 3) |
| Exemplary excerpts | teaching material | lecture notes |

## Write the handoff

Copy `LAB-NOTES.md` to the course repo as
`Grading/Feedback/<course>-d<NN>-lab-notes.md`, then write one file,
`Grading/Feedback/<course>-d<NN>-handoff.md`, grouped by stage, each
item with the evidence (rates, counts, which students' quotes) and a proposed
change written to paste or ignore.

The Lab Manager files it where next year notes live:

- ITS 4750: `Deliverable-N/memory/` and `NEXT-YEAR-RUBRICS.md`
- ITS 3100: the deliverable's `FEEDBACK.md`, under a "From <term> grading"
  section, as D01 already does

Next year notes, not edits. A posted lab and its rubric do not change mid term.
