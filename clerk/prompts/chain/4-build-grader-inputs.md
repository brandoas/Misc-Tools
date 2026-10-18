# Stage 4: Build the Clerk inputs for a deliverable

Replaces the old `build-grader-inputs.md`, now removed. Run in the Lab NN Manager session
after the rubric is posted and the Evidence Map exists.

You are writing the instrument for the Clerk, not the grader. Read
`INPUT-SPEC.md` in this same folder before starting and follow it exactly.

Output:

```text
<course repo>/Grading/Cards/<course>-d<NN>.md       e.g. 4750-d04.md
<course repo>/Grading/Cards/<course>-d<NN>-lab.md   e.g. 4750-d04-lab.md
```

## Sources, and what each is trusted for

| Source | Trusted for |
|---|---|
| Live Canvas rubric (pull it, do not describe it) | criteria, heading text, points. The card mirrors it exactly. |
| Handout | what the student was asked: Objectives verbatim, the steps that produce evidence |
| Evidence Map (`Grading/QA/<course>-dNN-evidence.md`) | what correct work looks like: invariants, per student rules, negative controls, traps |
| Existing grader card, if any | Critique bullets written against real submissions. Not trusted for criteria or points. |
| `Grading/Feedback/` from a previous run of this deliverable, if any | which bullets failed most of a class, and why |

If the Evidence Map is missing, say so at the top of the hand back and build
from the handout, marking every bullet that rests on the handout alone.

If two sources disagree about criteria or points, Canvas wins and you report
the disagreement. If the card would grade something the handout never asked
for, stop and report it; that is a lab defect, not a card to write.

## How the rating works, because it changes how you write

`judge.rate()` in code, not the model, decides the rating from the bullets:

- **Complete only if every Evidence bullet is satisfied.** There are no optional
  bullets. A "nice to have" bullet costs every student who skipped it a point.
- **Missing below one third** of bullets satisfied.
- Each satisfied bullet needs a verbatim quote from the report, checked in code.
  A bullet that can only be satisfied by an image cannot be quoted.

So: every bullet is something the Objective genuinely requires, and the count is
chosen deliberately. Six to eight per criterion; fewer for small criteria is fine.

## Writing Evidence bullets from the Evidence Map

1. **Start from the invariants.** Command names, field names, states, message
   types. These become bullets that name the exact string: "`show ip ospf
   neighbor` shows Full for every adjacency".
2. **Per student values become rules, never values.** "Client address inside
   the student's delegated prefix", "IPv4 gateway is the last usable address".
   Never put a reference address, prefix or lease in a bullet.
3. **Negative controls become paired bullets.** One for the before or teardown
   state, one for the after. These are the bullets a fluent student who did no
   work cannot pass.
4. **Traps:**
   - "Looks right, is wrong" becomes a Critique bullet, and if it is common, an
     Evidence bullet that excludes it ("NAT64 tested from a LAN2 client, not from
     the router").
   - "Looks wrong, is correct" must not be able to fail any bullet. Word the
     bullets around it, and note it in the card's top comment for the human
     reviewer. Do not put it under Critique; Critique is read as failure modes.
   - Names the GNS3 GUI rewrites, prefixes that move, and similar: never in a
     bullet.
5. **Anchor every "explain" bullet.** "Student explains X" is passed by good
   writing. Tie it to the artifact: "The renewal is identified in the capture
   as a REQUEST/ACK pair with no DISCOVER", "The why names the missing return
   route on VyOS-1".
6. **One fact per bullet.** Split anything joined by "and".
7. **Text, not pictures.** Bullets ask for command output, captures and configs
   as text. Diagrams and browser windows are the only legitimate images, and
   the Clerk reads those through the vision stage.

## Critique bullets

The known failure modes, written as what is wrong, not as advice. They seed the
comment on an Acceptable. Sources in order: the Evidence Map's "looks right, is
wrong" traps, previous lab notes, the existing grader card's Critique list.

## Report Standards

Use the course's standard block and its machine checks (`check N: name`, names
from `clerk/checks.py`). Bullets a check answers never reach the model. Do not
ask the model about file format, fonts, or whether something is a screenshot.

## lab.md

Mechanical: one `## Task N - Title` per task, the Objective line verbatim, and
the numbered steps that produce evidence. Drop setup prose and cleanup. Task
numbering identical to the handout, since `tasks:` joins on it.

## Canary

If the student facing handout carries an AI use marker, put the exact string in
the card's `canary` field and nowhere else. Never in a bullet, a comment, or
prose. Note in the hand back if the deliverable itself requires LLM use, since a
model fingerprint then means nothing.

## Top comment on the card

An HTML comment above the first criterion, for the human signing it:
sources used, any disagreement resolved against Canvas, "not a fault" notes
from the Evidence Map, and bullets resting on the handout alone.

## Lint, then stop

If `Misc-Tools/clerk` is on this machine, run from it:

```text
python -m clerk card lint <course repo>/Grading/Cards/<course>-d<NN>.md \
    --lab <course repo>/Grading/Cards/<course>-d<NN>-lab.md
```

and fix what it reports. If it is not, check the INPUT-SPEC rules by hand and
say in the hand back that the card is unlinted; the Clerk context lints it. Leave `reviewed_by` and `reviewed` empty. You do not sign.

## Hand back to Brandon

- Which decomposition Canvas holds, and whether the old grading material agreed
- Bullets you were unsure of, and why
- Any task with no gradeable artifact
- Any Objective the Evidence Map says cannot be proven here
- Whether there is a canary, and whether it means anything for this lab
- The test: could a human reading only the card and a report reach the same
  rating you would? If not, say which criterion is underspecified.
