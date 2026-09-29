"""Aggregate a graded run into notes for fixing the lab next time it runs.

The per student sheets say what each student did. This says what the *lab* did,
which is the thing that gets lost between semesters: by spring nobody remembers
that two thirds of the class missed the same bullet, and the handout ships
again unchanged.

The organising idea is a failure rate per evidence bullet, not per criterion. A
criterion at 45 percent Missing tells you something is wrong somewhere in it. A
single bullet failed by 21 of 29 students tells you which sentence to rewrite.

Rates are read as follows, and the thresholds are judgement calls worth arguing
with rather than laws:

- **above 60 percent**: almost never twenty students independently failing. Either
  the bullet asks for something the handout never asked for, or it asks for
  something the grader cannot see, or the instruction did not land at all.
- **40 to 60 percent**: the instruction is probably ambiguous, or the evidence it
  wants is easy to do and easy to forget to write down.
- **below 25 percent**: normal spread. Students missing things.

Nothing here is a grade. It is a to do list for the handout.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HIGH, MEDIUM = 0.60, 0.40


def _load(run_path: Path) -> tuple[list[dict], dict]:
    verdicts = []
    for f in sorted((run_path / "verdicts").glob("*.json")):
        verdicts.append({"student": f.stem,
                         "criteria": json.loads(f.read_text(encoding="utf-8"))})
    roster_file = run_path / "roster.json"
    roster = json.loads(roster_file.read_text(encoding="utf-8")) if roster_file.is_file() else {}
    return verdicts, roster


def build(run_path: Path, card, lab) -> str:
    verdicts, roster = _load(run_path)
    n = len(verdicts)
    if not n:
        return "No verdicts in this run.\n"

    # Failure rate per evidence bullet.
    per_bullet: dict[tuple[str, str], int] = Counter()
    per_criterion: dict[str, Counter] = defaultdict(Counter)
    for v in verdicts:
        for x in v["criteria"]:
            per_criterion[x["criterion"]][x["rating"]] += 1
            for m in x["missing"]:
                # Machine checks append a parenthetical reason; group on the bullet.
                bullet = m.split(" (")[0]
                per_bullet[(x["criterion"], bullet)] += 1

    course = card.meta.get("course", "")
    deliv = card.meta.get("deliverable", "")
    out = [
        f"# {course} Deliverable {deliv}: notes for the next run",
        "",
        f"Generated {date.today().isoformat()} from {n} graded submissions "
        f"by `clerk notes`.",
        "",
        "**This is a to do list for the handout and the card, not a record of "
        "grades.** Every rate below is the share of the class that did not "
        "satisfy one evidence bullet. A bullet most of the class missed is "
        "usually a defect in what was asked, not twenty independent failures.",
        "",
    ]

    ranked = sorted(per_bullet.items(), key=lambda kv: -kv[1])
    high = [(k, c) for k, c in ranked if c / n >= HIGH]
    med = [(k, c) for k, c in ranked if MEDIUM <= c / n < HIGH]

    out += ["## Fix these first", ""]
    if high:
        out.append(f"Missed by {int(HIGH * 100)} percent or more of the class. At "
                   f"this rate, look at the instruction before the students.")
        out.append("")
        out.append("| Rate | Criterion | Evidence bullet |")
        out.append("|---|---|---|")
        for (crit, bullet), c in high:
            out.append(f"| **{c}/{n}** ({c/n:.0%}) | {crit} | {bullet} |")
        out.append("")
    else:
        out += ["Nothing was missed by most of the class.", ""]

    if med:
        out += ["## Worth a look", "",
                f"Missed by {int(MEDIUM * 100)} to {int(HIGH * 100)} percent. "
                f"Usually an ambiguous instruction, or evidence that is easy to "
                f"produce and easy to forget to write down.", "",
                "| Rate | Criterion | Evidence bullet |", "|---|---|---|"]
        for (crit, bullet), c in med:
            out.append(f"| {c}/{n} ({c/n:.0%}) | {crit} | {bullet} |")
        out.append("")

    # Criteria nobody completed: usually the card, not the class.
    never = [name for name, counts in per_criterion.items()
             if counts.get("Complete", 0) == 0]
    if never:
        out += ["## Nobody scored Complete", "",
                "Not one student in the class met every bullet on these. Either "
                "the bar is set somewhere the lab does not reach, or the "
                "criterion carries more bullets than one task can evidence.", ""]
        for name in never:
            crit = card.criterion(name)
            out.append(f"- **{name}** ({len(crit.evidence)} evidence bullets)")
        out.append("")

    # Handout defects the card recorded while it was being built.
    missing_obj = [c.name for c in card.criteria if not c.objective]
    derived = [c.name for c in card.criteria if "DERIVED" in (c.objective or "")]
    lab_no_obj = [t.number for t in lab.tasks if not t.objective] if lab else []
    if missing_obj or derived or lab_no_obj:
        out += ["## Handout defects", ""]
        if lab_no_obj:
            out.append(f"- Tasks {', '.join(str(t) for t in lab_no_obj)} carry no "
                       f"**Objective** line in the handout. Every other task does. "
                       f"Students were given no statement of what those tasks are "
                       f"for, and the grader has nothing to measure against.")
        for name in derived:
            out.append(f"- **{name}** is graded against a *derived* objective, "
                       f"because the handout states none. Write a real one.")
        for name in missing_obj:
            out.append(f"- **{name}** has no objective on the card.")
        out.append("")

    # Formatting signals, measured rather than judged.
    meta_dir = run_path / "extract"
    no_mono, screenshot_albums = [], []
    for v in verdicts:
        mf = meta_dir / f"{v['student']}.meta.json"
        if not mf.is_file():
            continue
        m = json.loads(mf.read_text(encoding="utf-8"))
        name = roster.get(v["student"], {}).get("name", v["student"])
        if m.get("monospace_ratio", 0) == 0:
            no_mono.append(name)
        imgs = len(m.get("images", []))
        if imgs >= 8 and m.get("monospace_ratio", 0) == 0:
            screenshot_albums.append(f"{name} ({imgs} images)")

    if no_mono or screenshot_albums:
        out += ["## Formatting, measured not judged", ""]
        if no_mono:
            out.append(f"- **{len(no_mono)} of {n} submitted with no fixed width "
                       f"text anywhere.** Command output was not pasted as text by "
                       f"any of them. If that is meant to be a hard requirement, "
                       f"the handout should show an example of what is wanted.")
            out.append(f"  {', '.join(sorted(no_mono))}")
        if screenshot_albums:
            out.append(f"- **{len(screenshot_albums)} submitted a screenshot album**: "
                       f"eight or more images and no text formatting at all. These "
                       f"cannot be graded from text and are close to ungradeable "
                       f"without reading every image.")
            out.append(f"  {', '.join(sorted(screenshot_albums))}")
        out.append("")

    out += ["## Where the class landed", "",
            "| Criterion | Complete | Acceptable | Missing |", "|---|---|---|---|"]
    for c in card.criteria:
        k = per_criterion.get(c.name, Counter())
        out.append(f"| {c.name} | {k['Complete']} | {k['Acceptable']} | {k['Missing']} |")
    out.append("")

    out += ["---", "",
            "Rates come from the grader's reading of each report and inherit its "
            "limits. A bullet whose evidence is usually a screenshot will show a "
            "high failure rate whenever the image pass has not been run, so check "
            "what the evidence actually looks like before rewriting an "
            "instruction.", ""]
    return "\n".join(out)


def cmd_notes(args) -> int:
    from .__main__ import Run
    from . import card as card_mod, lab as lab_mod

    run = Run(args.run)
    card = run.load_card(require_signed=False)
    lab = lab_mod.load(run.lab_path) if run.lab_path.is_file() else None
    text = build(run.path, card, lab)

    dest = Path(args.out) if args.out else run.path / "LAB-NOTES.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(f"wrote {dest}")
    print()
    print(text)
    return 0
