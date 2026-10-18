# Paste into the course CLAUDE.md (ITS-3100-Devel and ITS-4750-Infrastructure)

## Assessment chain

Every graded lab passes through six artifacts, in this order. Each one is built
from the one before it, and a defect found downstream is fixed at the earliest
link that caused it, not patched where it showed up.

1. **Objective**: the `> [!IMPORTANT]` `**Objective:**` line that opens each
   task in the handout. It is the standard the student is graded against.
2. **Evidence Map**: `Grading/QA/<course>-dNN-evidence.md`, from the lab's QA rig. What correct work
   actually looks like, from the reference build.
3. **Rubric**: the Canvas rubric JSON in `Grading/Rubric/`.
   Canvas is the authority on criteria and points.
4. **Card and lab.md**: `Grading/Cards/<course>-dNN.md` and `<course>-dNN-lab.md`. The instrument.
5. **Calibration**: the card graded against fixtures built from the Evidence Map,
   then signed by Brandon.
6. **Lab notes**: after grading, `Grading/Feedback/`, what the cohort says
   about the lab, then filed as next year notes.

`Grading/` holds everything the Clerk needs. Intermediate files (Clerk runs,
student submissions) live in OneDrive under `<course>/<term>/Grading/`, never
in a repo. See `Grading/README.md`.

Authority, when sources disagree:

- What the student was **asked**: the handout. Nothing gets graded that the
  handout did not ask for.
- What **correct** looks like: the QA rig and its Evidence Map.
- **Criteria and points**: the live Canvas rubric.
- Prior grader cards and grading guides are drafts, not authorities. They were
  largely machine written and carry real errors.

Ownership:

- The Lab NN Manager session owns Objectives, the rubric and the card for its
  lab, and nothing for any other lab.
- The QA context owns the Evidence Map. It hands it across; it does not write
  rubric or card text.
- The Clerk owns calibration and the lab notes, and hands the notes back to the
  Lab Manager.

Mid semester rule: once a lab is posted, Objectives and rubrics are not edited.
Anything found goes into next year notes. Cards can be fixed, because a card
only changes how the instructor grades, and a fixed card has to be re-signed.

Prompts for each stage are in `Grading/prompts/`, with `INPUT-SPEC.md`, the card
format. They are copies; the master is `Misc-Tools/clerk/prompts/chain/`. Edit
the master, not the copy.
