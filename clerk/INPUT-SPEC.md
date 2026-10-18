# Grader input specification

Normative. The grader reads exactly two files per deliverable and nothing else
about the course. Everything that varies between ITS 3100 and ITS 4750, and
between one deliverable and the next, lives in these two files.

| File | Holds | Authored by |
|---|---|---|
| `card.md` | The rubric criteria and the evidence that satisfies each one | The rubric development context, reviewed by a human |
| `lab.md` | The task context: what the student was asked to do | The rubric development context, mechanical |

Both are plain Markdown. Both are meant to be read and edited by hand. If the
grader produces a bad result, the fix is almost always in `card.md`, not in the
code.

## The review gate

`card.md` carries `reviewed_by` and `reviewed` in its front matter. **The grader
refuses to run against a card whose `reviewed` date is older than the file's own
modification time.** Edit the card, the signature goes stale, and the tool stops
until a human signs it again.

This is deliberate. The grading guides in the course repos were largely machine
drafted and carry errors, including point decompositions that contradict the
Canvas rubric they claim to mirror. A card is a graded instrument. It does not
get used until someone has read it.

## card.md

### Front matter

```yaml
---
course: ITS-3100
deliverable: "01"
title: IPv6
canvas_rubric: 64804
canvas_rubric_title: Deliverable 01 - Report
points: 90
ratings:
  complete: full
  acceptable: minus_one
  missing: 0
canary: null
reviewed_by: saundeb1
reviewed: 2026-09-26
---
```

| Key | Meaning |
|---|---|
| `course` | Repo prefix, `ITS-3100` or `ITS-4750` |
| `deliverable` | Two digit string, quoted, `"01"` |
| `canvas_rubric` | The Canvas rubric id this card mirrors. **The Canvas rubric is the authority.** |
| `points` | Total, must equal the sum of the criteria below |
| `ratings` | How the three ratings score. `minus_one` means Acceptable is full minus one and requires a comment. |
| `canary` | The AI use marker string for this lab, or `null`. See "Canaries" below. |
| `reviewed_by`, `reviewed` | The human gate |

### Criteria

One `##` heading per Canvas rubric criterion, with its point value in
parentheses. The heading text must match the Canvas criterion description, so a
verdict maps to a rubric row without guesswork.

```markdown
## Task 3 - SLAAC and DHCPv6 on the WAN (10)

tasks: [3]
objective: Prove that SLAAC, DHCPv6, and IPv6 Routing properly function.

### Evidence

- Names which mechanism produced each address, not just a list of addresses
- Link-local address identified as fe80::/10
- SLAAC autoconf address on eth0 identified as such
- DHCPv6 address on eth0 distinguished from the autoconf address
- Delegated /64s on eth1 and eth2 traced back to the WAN delegation
- sla-id 0 and 1 visible and explained as the difference between the two LANs

### Critique

- show interfaces output pasted with no analysis
- DHCPv6 WAN address confused with the delegated prefix
- Link-local mistaken for a global address
- Addresses listed without naming the acquiring mechanism
```

`objective:` is **the Objective line from the student's handout, copied
verbatim**, the one in the task's IMPORTANT callout. It is required.

This is the standard the criterion is graded against, because it is what the
student was actually told to achieve. The Evidence bullets only measure it. The
judge is given the objective first and the checklist second, and told that the
objective wins where the two pull apart.

Lint compares the card's objective against the handout's own line for each task
in `tasks:`, and reports a mismatch. A criterion whose objective appears nowhere
in the handout is grading students on an instruction they never received, which
is a lab defect to fix, not a standard to hold. ITS 3100 Deliverable 01 shipped
with exactly that: a live 5 point rubric row for a question the handout never
asked.

`tasks:` names the lab tasks this criterion draws on, as a list of integers. The
grader uses it to pull the matching sections out of `lab.md` so the judge sees
what the student was asked to do, not only what the rubric wants. Omit it only
when a criterion spans the whole report, for example a report standards
criterion.

### Writing Evidence bullets

The Evidence list is the whole instrument. Every bullet is a question the judge
asks of the report, so each one has to be answerable from the report alone.

**A good bullet is observable.** "ping6 to 2606:4700:4700::1111 succeeds" can be
found or not found. "Student understands SLAAC" cannot.

**A good bullet is a single fact.** Split anything joined by "and". A bullet that
asks two questions gets one rating, and you lose the information about which
half failed.

**A good bullet names the artifact.** "show configuration commands | match
name-server output present" beats "DNS is configured", because the first tells
the judge what string to look for.

**A good bullet survives a student who writes well but did nothing.** The
failure mode of an AI grader is rewarding fluent prose. Bullets that demand a
specific address, a specific command output, or a specific number resist that.
Bullets that ask whether something was "explained clearly" do not.

Six to eight bullets per criterion is the working range. Fewer, and the rating
is coarse. More, and the criterion should probably be two criteria.

### Writing Critique bullets

The Critique list is the set of known failure modes, and it does double duty: it
tells the judge what a partial answer looks like, and it seeds the comment that
goes back to the student on an Acceptable.

Take these from real grading experience wherever you have it. The Critique
bullets already in the course grader cards are the best source, since they were
written against actual submissions.

### Canaries

Some labs carry a hidden marker in the README that only surfaces if a student
pasted the lab into a chatbot. Put the exact string in the `canary` front matter
field.

**The grader handles canaries entirely in code, before any prompt is built.** A
submission containing the marker is quarantined, is never sent to a model, gets
no rating, and appears in the cohort report as a bare student name under
"quarantined" with no quotation of the marker. The marker string never enters a
prompt, a verdict, or a comment.

Do not write canary handling into Evidence or Critique bullets. A model told not
to mention a string will eventually mention it.

## lab.md

Mechanical. It is the deliverable handout reduced to what the judge needs, which
is the per task Objective and the numbered steps that produce evidence.

```markdown
---
course: ITS-3100
deliverable: "01"
source: Deliverable 01 - IPv6.md
---

## Task 3 - IPv6 router WAN configuration with SLAAC

Objective: Prove that SLAAC, DHCPv6, and IPv6 Routing properly function.

Steps 5 to 10.

5. Configure eth0 for SLAAC with `set interfaces ethernet eth0 ipv6 address autoconf`
6. ...
10. Break each address into its prefix and interface ID, and explain how it was acquired
```

Keep the steps that ask the student to produce, capture, or explain something.
Drop setup prose, links to tech nuggets, and cleanup steps. The section headings
must carry the task number in the same form the card's `tasks:` list uses, since
that is how the two files join.

## What the grader gives back

Per criterion, per student:

```json
{
  "criterion": "Address Acquisition Analysis",
  "points": 15,
  "rating": "Acceptable",
  "evidence": ["verbatim quote from the report", "..."],
  "missing": ["sla-id difference between eth1 and eth2 explained"],
  "comment": "Addresses are all present, but the DHCPv6 address on eth0 is labelled as the delegated prefix.",
  "confidence": "high",
  "exemplary": false
}
```

Every string in `evidence` is checked against the extracted report text. A quote
that is not found verbatim means the model fabricated it, so the criterion is
voided and flagged for review rather than scored. That check is what makes a
rating defensible when a student challenges it.

`exemplary` is a separate and higher bar than `Complete`. It means the work is
worth showing a future class, and it feeds the cohort report.

## Lint

```
clerk card lint <course repo>/Grading/Cards/3100-d01.md
```

Checks that criteria points sum to `points`, that the front matter is complete,
that every criterion has both an Evidence and a Critique list, that `tasks:`
references exist in `lab.md`, and that the review signature is current. It does
not check that the card is correct. Only a human does that.
