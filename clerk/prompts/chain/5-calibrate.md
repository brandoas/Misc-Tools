# Stage 5: Calibrate the card before it is signed

Run in the Clerk context, against an unsigned card from Stage 4. Nothing here
grades a real student. The goal is a number Brandon can sign against.

## Read first

- `Grading/Cards/<course>-d<NN>.md` and `<course>-d<NN>-lab.md` in the course repo
- The Evidence Map for this lab, which is where fixture content comes from
- `ITS-3100-Devel/Grading/Cards/fixtures/make_3100_d01.py`, the 3100 D01
  generator, as the model

## Build the fixtures

Write `Grading/Cards/fixtures/make_<course>_d<NN>.py` in the course repo,
following the existing generator. It takes the run directory as its argument.
The run directory is OneDrive `<course>/<term>/Grading/<course>-d<NN>-fixtures/`,
never the repo. One
coordinated allocation used across every fixture, so a report reads like one
network. Take its values from the Evidence Map's per student rules, not from
the reference build, and choose values that differ from the reference so a card
bullet that quietly hardcodes a reference value shows up as a failure.

Command output in the fixtures is the Evidence Map's reference output,
re-addressed to the fixture allocation. Do not invent output. Real output is the
only thing that tests whether a bullet's wording matches what the command
actually prints.

The seven fixtures:

| Fixture | Written to | Expected |
|---|---|---|
| `strong` | satisfy every bullet | Complete throughout |
| `thin` | every artifact present, no analysis | Acceptable or Missing on analysis bullets |
| `partial` | one planted gap per criterion, each a Critique bullet | Acceptable where planted |
| `fluent` | confident, well written prose, no command output and no negative controls | Missing or Acceptable throughout. If this one scores Complete anywhere, that criterion's bullets reward writing |
| `traps` | correct work that hits every "looks wrong, is correct" item in the Evidence Map | Complete throughout. Any deduction is a bullet that needs rewording |
| `screenshots` | correct content, command output pasted as images | Report Standards fails; task criteria per the card |
| `missing` | two tasks absent | Missing on those criteria |

`fluent` and `traps` are the two the 3100 D01 set lacks, and they test exactly
the two failure modes this chain exists to prevent.

`expected.json` records the rating per fixture per criterion, and per bullet
where it matters.

## Run

```text
python Grading/Cards/fixtures/make_<course>_d<NN>.py $RUN
clerk extract  $RUN
clerk vision   $RUN
clerk assemble $RUN
clerk judge    $RUN --unsigned --host spark
clerk calibrate $RUN
```

## Report back

- The calibrate score, per fixture and per criterion
- Every bullet that disagreed with `expected.json`, and whether the fault is the
  bullet's wording, the fixture, or the judge
- Proposed bullet rewrites for the first kind. Edit the card only if Brandon
  says so, since an edit invalidates any signature.

If real reports from this deliverable exist and Brandon has hand graded some,
run those too and give the mean absolute gap per criterion. That number beats
the fixtures; the fixtures are cleaner than real work.

The card is ready to sign when `strong` and `traps` are Complete throughout,
`fluent` is nowhere Complete, and every planted gap in `partial` is found.
