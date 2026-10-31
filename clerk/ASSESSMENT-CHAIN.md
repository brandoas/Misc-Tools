# The assessment chain: Objectives, Evidence, Rubric, Card

Proposal, 2026-10-18. Nothing here changes a lab, a rubric or a card. It is a
workflow and a set of prompts for the course level contexts
(`ITS-3100-Devel`, `ITS-4750-Infrastructure`) and the per lab Manager sessions
that work inside them.

## The problem in one paragraph

The Clerk card is the last link in a chain, and today it is built from the two
weakest sources in that chain: a human grader card that was largely machine
drafted, and the handout. The one source that actually knows what correct work
looks like, the QA rig, is never consulted. The QA rigs hold real output from a
working reference build, the shape rules for per student addresses, the negative
controls, and a long list of traps that look like faults and are not, or look
right and are wrong. None of that reaches an Evidence bullet. Upstream of that,
some task Objectives cannot be proven by anything a student could put in a
report, so every downstream artifact inherits a standard nobody can measure.

## The chain

```
1 Objective      Lab Manager    handout IMPORTANT callout, one per task
2 Evidence Map   QA context     Grading/QA/<course>-dNN-evidence.md
3 Rubric         Lab Manager    Grading/Rubric/, task mapped
4 Card + lab.md  Lab Manager    Grading/Cards/
5 Calibrate      Clerk          fixtures from the Evidence Map, then sign
6 Close loop     Clerk -> LM    Grading/Feedback/, then next year notes
```

Each stage reads files and writes one file. Each stage has one owner context.
The Evidence Map is the new artifact and the join point: it is the only thing
the QA context hands across, so the Lab Manager never has to read QA code and
the QA context never has to touch a rubric. That keeps the one session per lab
rule intact.

| Stage | Prompt | Runs in | Writes |
|---|---|---|---|
| 0 | `prompts/chain/0-course-context.md` | pasted once into each course CLAUDE.md | nothing |
| 1 | `prompts/chain/1-objectives.md` | Lab NN Manager | Objective lines (next year notes if mid term) |
| 2 | `prompts/chain/2-evidence-map.md` | QA context for that lab | `Grading/QA/` |
| 3 | `prompts/chain/3-rubric.md` | Lab NN Manager | `Grading/Rubric/` |
| 4 | `prompts/chain/4-build-grader-inputs.md` | Lab NN Manager | `Grading/Cards/` |
| 5 | `prompts/chain/5-calibrate.md` | Clerk | `Grading/Cards/fixtures/`, run in OneDrive |
| 6 | `prompts/chain/6-close-the-loop.md` | Clerk, handed to Lab NN Manager | `Grading/Feedback/` |

The prompts are copied into each course repo's `Grading/prompts/` so a machine
with only that repo can run them. Edit the masters here and run
`./sync-prompts.sh`; see `SYNC.md`.

Stage 4 replaces the old `prompts/build-grader-inputs.md` and its copy at
`ITS-3100-Devel/BUILD-GRADER-INPUTS.md`, both removed 2026-10-18.

## Where things live

| | ITS 4750 | ITS 3100 |
|---|---|---|
| Handout (Objectives) | `ITS-4750-Lab-NN/README.md` | `ITS-3100-Devel/Deliverable NN - Name.md`, then the student facing `ITS-3100` copy |
| Authoring rules | `ITS-4750-Infrastructure/LAB-AUTHORING.md` | `ITS-3100-Devel/CLAUDE.md` house style |
| QA rig | `ITS-4750-Infrastructure/Deliverable-N/qa/` | `ITS-3100-Devel/Infrastructure/Deliverable NN - Name/` |
| QA findings | `qa/decisions.md`, `qa/answer-key/` | `OBSERVE.md`, `FEEDBACK.md`, `run.py` proofs |
| Grading data | `ITS-4750-Infrastructure/Grading/{QA,Rubric,Cards,Feedback}` | `ITS-3100-Devel/Grading/{QA,Rubric,Cards,Feedback}` |
| Evidence Map (new) | `Grading/QA/4750-dNN-evidence.md` | `Grading/QA/3100-dNN-evidence.md` |
| Rubric JSON | `Grading/Rubric/4750-dNN-*.json` | `Grading/Rubric/3100-dNN-*.json` |
| Human card | `Grading/Cards/Lab-NN-*.md` | `Grading/Cards/Deliverable NN - Grader Card.md` |
| Clerk inputs | `Grading/Cards/4750-dNN.md`, `4750-dNN-lab.md` | `Grading/Cards/3100-dNN.md`, `3100-dNN-lab.md` |
| Clerk runs (intermediate) | OneDrive `ITS 4750/<term>/Grading/4750-dNN/` | OneDrive `ITS 3100/<term>/Grading/3100-dNN/` |
| Post grading notes | `Grading/Feedback/` | `Grading/Feedback/` |
| Next year notes | `Deliverable-N/memory/`, `NEXT-YEAR-RUBRICS.md` | that deliverable's `FEEDBACK.md`, "From grading" section |

## What the survey found

These are the specific reasons for the changes in the prompts.

**The QA rigs never reach the card.** The old `build-grader-inputs.md` trusted, in
order, the existing grader card, the handout, and the lab README. The QA
material is the most reliable of all of them and is absent. Examples of what is
being left on the table:

- Lab 03's `answer-key/reference-build.yml` says outright that every interior
  number is "an" answer, not "the" answer, and that what the QA enforces is the
  shape. That is exactly the rule an Evidence bullet needs and does not have.
- 3100 D01 `OBSERVE.md`: the delegated `483f:` prefix changes on its own, so a
  different one in a report is correct. A bullet written against the reference
  value fails every student.
- 3100 D04 `OBSERVE.md`: the before state ping failure is the control the
  tunnel is measured against, and `nmcli connection down wg0` is the only
  teardown that proves anything. Both are perfect fluency resistant bullets.
- 3100 D01 `FEEDBACK.md`: do not test NAT64 by pinging from the router. A
  report that does is wrong in a way a generic bullet will not catch.
- 4750 Lab 5: the GNS3 GUI refuses underscores, so every correctly built
  student project says `SN-Client`. The automatic grader failed every student
  on it. A card bullet naming `SN_Client` would do the same.

**Some Objectives cannot be proven.** The Clerk judge is told the objective
wins over the checklist, so an objective that names no observable outcome
leaves the judge with nothing to hold.

- 4750 Lab 04 Task 2: "Interact with the GNS3 API directly."
- 4750 Lab 04 Task 4: "Practice running Ansible playbooks and reading their
  output at increasing levels of verbosity."
- 3100 D02 Tasks 8 and 9 had no Objective at all; the card carries derived
  wording the student never read.

Compare 4750 Lab 04 Task 6, "Configure every device in the network with
Ansible, and prove the lab path works end to end", which names its proof.

**Bullets that a fluent student passes without doing the work.** From the
current cards: "Code explained in the student's words", "Narrative connects the
evidence", "Storage method stated", "Student states why: ...", "One nuance
beyond DORA". Each can be satisfied by writing well. Each needs an anchor: a
named field, value, command, or a before and after pair.

**Every bullet gates Complete.** `judge.rate()` gives Complete only when every
bullet is satisfied, and Missing below one third. So an optional or "nice to
have" bullet is not optional: it costs every student who skipped it a point.
And the bullet count sets where the Missing floor sits. Bullet writing has to
be done knowing this.

**"No deduction" notes have no home.** The 4750 Lab 1 card puts "Item 21 hosts
failing to reach the internet is expected. No deduction" under Critique. The
Clerk feeds Critique to the judge as failure modes and seeds Acceptable
comments from it. The fix that needs no code change: write bullets so the
expected condition cannot fail them, and keep "not a fault" notes in the
card's top comment for the human reviewer.

**Two instruments with one name, again waiting to happen.** 3100 D01 had a
grader card and a grading guide that disagreed with each other and with Canvas.
4750 has `Grading/README.md` listing Lab 1 as a 5 by 15 rubric while
`Grading/Lab-01-DDI.md` describes a 9 criterion task mapped Grader B. Generating
the human card and the Clerk card from one source removes the class of problem.

**Path drift (fixed 2026-10-18).** The old prompt referred to `Canvas-Tools/clerk`
and `Canvas-Tools/course-admin`. They live in `Misc-Tools/`. There is also an older
`ITS-4750-Infrastructure/Canvas-Tools/canvas_api.py`. Rubric JSONs now live in
each course's `Grading/Rubric/` with a course prefix (`4750-d04-grader.json`).

**4750 has no Clerk cards yet.** Only `3100-d01.md` and `3100-d02.md`
exist. The 4750 cards in `Grading/` are in a "Full points / Critique" shape
that is close to Clerk format but not lint clean.

## Decisions for Brandon

Posed as questions, not settled here.

1. One card or two? The Clerk card format is already readable by a human
   ("a card someone can grade from by hand"). Should the human grader cards in
   `Grading/` and `Grading Guide/` be retired in favour of the Clerk card, or
   generated from it?
2. Should the Evidence Map be a hard gate, so no card gets built for a lab
   whose QA rig has not produced one, or advisory, so a card can still be built
   from the handout alone for labs with no rig (3100 D05 to D10, 4750 Labs 7
   to 11)?
3. Is it worth a small Clerk change to give "not a fault" notes their own card
   section, so the judge sees them as context rather than as failure modes?
4. For 4750 Labs 1 to 3 this term: build Clerk cards against the 5 by 15
   rubrics as posted, or wait for the Grader B rebuild next year?
