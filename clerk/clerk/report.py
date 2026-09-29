"""Render the two human facing outputs.

The per student sheet is what you grade from. The cohort report is what tells
you whether the lab worked.

Neither one posts anything. Every rating in here is a proposal, and the point of
rendering it this way is that disagreeing with it should take a glance, not a
re-read of the student's report.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .judge import Verdict


@dataclass
class StudentResult:
    student: str
    verdicts: list[Verdict] = field(default_factory=list)
    quarantined: bool = False
    monospace_ratio: float = 0.0
    image_kinds: Counter = field(default_factory=Counter)

    @property
    def awarded(self) -> int:
        return sum(v.awarded for v in self.verdicts)

    @property
    def possible(self) -> int:
        return sum(v.points for v in self.verdicts)

    @property
    def needs_review(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.confidence == "low"]


def _blockquote(quote: str, limit: int = 400) -> str:
    """Render a quote as a Markdown blockquote.

    Every line needs its own marker. Most evidence here is pasted command
    output, so a single leading '>' quotes the first line and dumps the rest
    into the body, which is unreadable exactly where the evidence matters most.
    """
    text = quote if len(quote) <= limit else quote[:limit].rstrip() + " ..."
    lines = ["> " + line if line.strip() else ">" for line in text.split("\n")]
    return "\n".join(lines)


def student_sheet(result: StudentResult, card) -> str:
    """The per student review sheet."""
    if result.quarantined:
        return (
            f"# {result.student}\n\n"
            f"**Not graded.** This submission is quarantined and was never sent "
            f"to a model. Review it yourself.\n"
        )

    out = [f"# {result.student}", ""]
    out.append(f"**Proposed: {result.awarded} of {result.possible}**")
    if result.needs_review:
        out.append(
            f"\n> {len(result.needs_review)} criterion needs your eyes before "
            f"this score means anything. See the flagged rows below."
        )
    out.append("")

    out.append("| Criterion | Proposed | Points |")
    out.append("|---|---|---|")
    for v in result.verdicts:
        flag = " (review)" if v.confidence == "low" else ""
        out.append(f"| {v.criterion} | {v.rating}{flag} | {v.awarded} of {v.points} |")
    out.append("")

    if result.image_kinds:
        kinds = ", ".join(f"{n} {k}" for k, n in result.image_kinds.most_common())
        out.append(f"Images: {kinds}.")
        if result.image_kinds.get("terminal"):
            out.append(
                f"> {result.image_kinds['terminal']} image(s) look like terminal "
                f"screenshots. The report guidelines ask for command output as "
                f"fixed width text, so check whether that is a deduction."
            )
        out.append("")

    for v in result.verdicts:
        out.append(f"## {v.criterion} ({v.points}) : {v.rating}")
        out.append("")
        if v.voided:
            out.append("**Flagged. The model produced unsupported findings:**")
            out.extend(f"- {reason}" for reason in v.voided)
            out.append("")
            out.append(
                "This rating is not usable as it stands. The quotes below are "
                "the ones that did verify."
            )
            out.append("")
        if v.evidence:
            out.append("Evidence found:")
            out.append("")
            for quote in v.evidence:
                out.append(_blockquote(quote))
                out.append("")
        if v.missing:
            out.append("Not found:")
            out.extend(f"- {m}" for m in v.missing)
            out.append("")
        if v.comment and v.rating == "Acceptable":
            out.append(f"Draft comment: {v.comment}")
            out.append("")
        if v.exemplary:
            out.append("Marked exemplary. Candidate for teaching material.")
            out.append("")

    return "\n".join(out)


def cohort_report(results: list[StudentResult], card, *, quarantined=None) -> str:
    """The class level report: what worked, what did not, what needs a human.

    The rating distribution is the point of this document. A criterion where
    most of the class came back Missing is a lab or a lecture defect, not twenty
    student failures, and that is the one thing a pile of per student sheets
    will not tell you.
    """
    quarantined = quarantined or []
    graded = [r for r in results if not r.quarantined]

    out = [
        f"# {card.meta.get('course')} Deliverable {card.meta.get('deliverable')} "
        f": cohort report",
        "",
        f"{len(graded)} graded, {len(quarantined)} quarantined.",
        "",
        "Every rating here is a proposal from a local model, checked against "
        "verbatim quotes from each report. Nothing has been posted to Canvas.",
        "",
    ]

    by_criterion: dict[str, Counter] = defaultdict(Counter)
    exemplars: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in graded:
        for v in r.verdicts:
            by_criterion[v.criterion][v.rating] += 1
            if v.exemplary and v.evidence:
                exemplars[v.criterion].append((r.student, v.evidence[0]))

    out += ["## Where the class landed", "",
            "| Criterion | Complete | Acceptable | Missing | Missing % |",
            "|---|---|---|---|---|"]
    trouble: list[tuple[str, float]] = []
    for c in card.criteria:
        counts = by_criterion.get(c.name, Counter())
        total = sum(counts.values()) or 1
        pct = counts["Missing"] / total
        if pct >= 0.4:
            trouble.append((c.name, pct))
        out.append(
            f"| {c.name} | {counts['Complete']} | {counts['Acceptable']} | "
            f"{counts['Missing']} | {pct:.0%} |"
        )
    out.append("")

    if trouble:
        out += ["## Look at the lab, not the students", ""]
        out.append(
            "These criteria were Missing for 40 percent or more of the class. "
            "At that rate the usual cause is an instruction that did not land, "
            "or a criterion asking for something the handout never asked for."
        )
        out.append("")
        for name, pct in sorted(trouble, key=lambda t: -t[1]):
            crit = card.criterion(name)
            tasks = ", ".join(str(t) for t in crit.tasks) or "whole report"
            out.append(f"- **{name}** ({pct:.0%} Missing). Tasks {tasks}.")
        out.append("")

    out += ["## Clear successes", ""]
    if exemplars:
        out.append(
            "Work the judge marked as worth showing a future class. Check each "
            "one before reusing it, and get the student's permission."
        )
        out.append("")
        for name, items in exemplars.items():
            out.append(f"### {name}")
            out.append("")
            for student, quote in items[:3]:
                out.append(f"**{student}**")
                out.append("")
                out.append(_blockquote(quote))
                out.append("")
    else:
        out.append("Nothing was marked exemplary in this run.")
        out.append("")

    out += ["## Critical misses: needs a human", ""]
    flagged = [(r, v) for r in graded for v in r.verdicts if v.confidence == "low"]
    if flagged:
        out.append(
            f"{len(flagged)} criterion rating(s) rest on findings that failed "
            f"the verbatim check, which means the model asserted evidence that "
            f"is not in the report. **These ratings are not usable.**"
        )
        out.append("")
        for r, v in flagged:
            out.append(f"- {r.student}, {v.criterion}: {v.voided[0]}")
        out.append("")
    else:
        out.append("No rating failed the verbatim check in this run.")
        out.append("")

    borderline = [
        (r, v) for r in graded for v in r.verdicts
        if v.rating == "Acceptable" and len(v.missing) == 1
    ]
    if borderline:
        out += ["### One bullet from Complete", "",
                "These missed a single checklist item. Either the work is a "
                "hair short, or the bullet is worded in a way the report cannot "
                "satisfy. Worth reading both ways before the next deliverable.",
                ""]
        for r, v in borderline[:15]:
            out.append(f"- {r.student}, {v.criterion}: {v.missing[0]}")
        out.append("")

    screenshots = [r for r in graded if r.image_kinds.get("terminal")]
    if screenshots:
        out += ["### Command output submitted as screenshots", "",
                "The report guidelines ask for CLI output as fixed width text. "
                "These reports carry images that look like terminal captures.",
                ""]
        for r in screenshots[:20]:
            out.append(f"- {r.student}: {r.image_kinds['terminal']} image(s)")
        out.append("")

    if quarantined:
        out += ["## Quarantined", "",
                "Not graded, never sent to a model. Handle these yourself.", ""]
        for q in quarantined:
            out.append(f"- {q.student}")
        out.append("")

    return "\n".join(out)
