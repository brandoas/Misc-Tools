"""Render the two human facing outputs.

The per student sheet is what you grade from. The cohort report is what tells
you whether the lab worked.

Neither one posts anything. Every rating in here is a proposal, and the point of
rendering it this way is that disagreeing with it should take a glance, not a
re-read of the student's report.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .judge import Verdict
from .md import table

#: A prose paragraph this long or longer is the student saying something, rather
#: than a caption, a heading or a stray line of output.
NARRATIVE_MIN_WORDS = 12


def narrative(dossier: str) -> list[str]:
    """The student's own prose, verbatim and in document order.

    Everything the grader decided is a restatement of their report. This is the
    report. Reading the two side by side is how you tell a criterion that was
    marked down fairly from one where the evidence was there and the grader
    missed it, which has happened enough times in this project to be the point.

    Fenced blocks are dropped, because those are command output rather than
    narrative, and so are headings, table rows and image placeholders. Nothing
    is reflowed or trimmed: a sentence that reads badly here reads badly in the
    submission.
    """
    import re
    from .extract import TERMINAL_RE

    body = re.sub(r"```.*?```", "", dossier, flags=re.S)
    body = re.sub(r"\[IMAGE-\d+[^\]]*\].*?\[/IMAGE-\d+\]", "", body, flags=re.S)
    out = []
    for para in re.split(r"\n\s*\n", body):
        text = " ".join(para.split())
        if not text or text.startswith(("#", "|", "[IMAGE", ">")):
            continue
        if len(text.split()) < NARRATIVE_MIN_WORDS:
            continue
        if TERMINAL_RE.search(para):
            continue
        out.append(text)
    return _rejoin(out)


#: A line that is genuinely a task HEADING, not a sentence that happens to open
#: with the words "Task 8".
#:
#: The difference matters: "Task 8 proved to be the most challenging part of the
#: lab" is prose, and treating it as a heading swallows the subject and files the
#: rest of the sentence under a task by accident. A heading is either marked as
#: one, or it is short and stops.
TASK_HEADING = re.compile(
    r"""^\s*(?:\d+[.)]\s*)?(?:
          \#{1,4}\s*\**\s*(?:task|part)\s*\#?\s*(\d+).{0,60}      # ## Task 8 - Title
        | \*\*\s*(?:task|part)\s*\#?\s*(\d+).{0,60}?\*\*          # **Task 8 - Title**
        | (?:task|part)\s*\#?\s*(\d+)\s*[-–—:.]\s*\S.{0,60} # Task 8 - Title
        | (?:task|part)\s*\#?\s*(\d+)\s*$                             # Task 8
        )\s*$""",
    re.I | re.M | re.X)


def _task_number(m) -> int:
    return int(next(g for g in m.groups() if g))


def narrative_by_task(dossier: str) -> dict:
    """Split the student's prose by the task they filed it under.

    A wall of prose with no attribution is nearly useless next to a per
    criterion verdict: the question a reader has is "what did they say about
    THIS task", not "what did they say". Students head their sections
    consistently enough to answer it, in both courses observed.

    Returns {task number: [passages]}, with 0 holding anything written before
    the first task heading.
    """
    import re
    sections: dict = {}
    marks = list(TASK_HEADING.finditer(dossier))
    if not marks:
        # No recognisable headings, so nothing can be attributed. Brandon,
        # 2026-10-02: if the header is not obvious, leave the prose out rather
        # than filing it under a guess.
        return {}
    # Prose before the first heading belongs to no task, so it is not shown.
    # Brandon, 2026-10-02: if the header is not obvious, leave the prose out.
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(dossier)
        num = _task_number(m)
        sections.setdefault(num, []).extend(narrative(dossier[m.end():end]))
    return {k: v for k, v in sections.items() if v}


def _rejoin(passages: list[str]) -> list[str]:
    """Re-join prose a PDF split across visual lines.

    A PDF has no paragraphs, only lines placed on a page, so a sentence that
    wrapped comes back as several passages broken mid clause: "...all the
    configuration works" / "for the VyOS-1 router." Those line breaks are layout
    and carry no meaning, so joining on them loses nothing.

    A passage is treated as a continuation when the one before it does not end a
    sentence and it does not begin one. Deliberately conservative: a wrongly
    joined pair reads oddly, where a wrongly split one is unreadable.
    """
    import re
    out: list[str] = []
    for text in passages:
        if (out
                and not re.search(r"[.!?:;]\s*$", out[-1])
                and not re.match(r"[A-Z0-9#\-*]", text)):
            out[-1] = out[-1] + " " + text
        else:
            out.append(text)
    return out


@dataclass
class StudentResult:
    student: str
    verdicts: list[Verdict] = field(default_factory=list)
    #: The submission carried this lab's AI use marker. It is graded like any
    #: other; the flag only puts a note on the review sheet and a name in the
    #: cohort report, both of which only the instructor reads.
    canary_flagged: bool = False
    monospace_ratio: float = 0.0
    image_kinds: Counter = field(default_factory=Counter)
    #: Images the vision pass never read, because they sat past the card's
    #: max_images cap. They are evidence the grade was not allowed to see, so
    #: the number is stated rather than left to be inferred from a silence.
    images_unread: int = 0
    #: Canvas originality report, if the assignment has one.
    similarity: dict | None = None
    #: The student's own prose, verbatim, keyed by the task they filed it under.
    #: Key 0 holds anything written before the first task heading.
    narrative: list[str] = field(default_factory=list)
    narrative_by_task: dict = field(default_factory=dict)

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
    out = [f"# {result.student}", ""]
    if result.canary_flagged:
        # The marker itself never appears here. A string quoted into a review
        # sheet is a string that can reach a student, and the course rule is to
        # say nothing about it in feedback.
        #
        # The banner sits above the score rather than in place of it. The work
        # is graded either way, and what the marker tells you is how the report
        # was written, which is yours to weigh rather than the grader's to
        # decide.
        out += [
            "> ## AI USE MARKER FOUND",
            ">",
            "> **This submission carries the marker for this lab.** It was "
            "graded like any other, and the ratings below rest on quotes from "
            "the report. The marker was never sent to a model.",
            ">",
            "> Do not mention the marker in feedback, and do not quote it "
            "anywhere a student could read it.",
            "",
        ]
    out.append(f"**Proposed: {result.awarded} of {result.possible}**")
    if result.needs_review:
        out.append(
            f"\n> {len(result.needs_review)} criterion needs your eyes before "
            f"this score means anything. See the flagged rows below."
        )
    out.append("")

    out.append(table(
        ["Criterion", "Proposed", "Points"],
        [[v.criterion,
          v.rating + (" (review)" if v.confidence == "low" else ""),
          f"{v.awarded} of {v.points}"] for v in result.verdicts]))
    out.append("")

    if result.similarity:
        sim = result.similarity
        state = sim.get("state") or "unknown"
        line = f"**Originality: {sim['score']:.0f}%**"
        if state not in ("scored", "acceptable", None):
            line += f"  (Turnitin state: `{state}`)"
        out.append(line)
        if sim.get("report_url"):
            out.append(f"[Open the originality report]({sim['report_url']})")
        out.append("")
        out.append(
            "> A lab report is structurally high similarity: every student runs "
            "the same commands from the same handout on identical infrastructure, "
            "so the commands, the handout wording and the software banners all "
            "match. Read this against the class, not against zero, and look at "
            "the analysis prose and the student's own addresses rather than the "
            "percentage."
        )
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
        if result.images_unread:
            out.append(
                f"> **{result.images_unread} of these image(s) were never read.** "
                f"They sat past the card's max_images cap, so nothing in them "
                f"could support a bullet. If a criterion below reads as missing "
                f"evidence, look at the images before believing it."
            )
        out.append("")

    if not result.narrative:
        # Saying nothing would read as "this section did not apply". No
        # narrative at all is a finding: the report is output with no student
        # voice in it, which is usually why the analysis bullets failed.
        out.append("## What the student wrote")
        out.append("")
        out.append("> **No narrative prose found.** Every paragraph in this "
                   "report is command output or a caption. Worth checking "
                   "against the criteria that ask the student to explain, "
                   "identify or compare something.")
        out.append("")
    elif not result.narrative_by_task:
        out.append("## What the student wrote")
        out.append("")
        out.append("> Prose is present but none of it sits under a recognisable "
                   "task heading, so it cannot be shown beside a criterion.")
        out.append("")

    for v in result.verdicts:
        # The award first, then the weight, and never a bare "(5)" next to a
        # rating word. "Task 2 - Network Core Deployment (5) : Acceptable" reads
        # as "scored 5, rated Acceptable", which is a contradiction: the 5 was
        # the criterion's weight and the student scored 4.
        out.append(f"## {v.criterion} - {v.rating}, {v.awarded} of {v.points}")
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
        said = []
        crit = next((c for c in card.criteria if c.name == v.criterion), None)
        for t in (crit.tasks if crit else []):
            said.extend(result.narrative_by_task.get(t, []))
        if said:
            out.append("What the student said about this task, verbatim:")
            out.append("")
            for passage in said[:6]:
                out.append(_blockquote(passage, limit=900))
                out.append("")

        if v.comment and v.rating == "Acceptable":
            out.append(f"Draft comment: {v.comment}")
            out.append("")
        if v.exemplary:
            out.append("Marked exemplary. Candidate for teaching material.")
            out.append("")

    return "\n".join(out)


def cohort_report(results: list[StudentResult], card, *, canary_hits=None,
                  roster: dict | None = None) -> str:
    """The class level report: what worked, what did not, what needs a human.

    The rating distribution is the point of this document. A criterion where
    most of the class came back Missing is a lab or a lecture defect, not twenty
    student failures, and that is the one thing a pile of per student sheets
    will not tell you.
    """
    canary_hits = canary_hits or []
    roster = roster or {}
    # Everything that produced a verdict is graded, marked submissions
    # included, so the distribution below covers the whole cohort.
    graded = list(results)

    out = [
        f"# {card.meta.get('course')} Deliverable {card.meta.get('deliverable')} "
        f": cohort report",
        "",
        f"{len(graded)} graded, {len(canary_hits)} carrying the AI use marker.",
        "",
        "Every rating here is a proposal from a local model, checked against "
        "verbatim quotes from each report. Nothing has been posted to Canvas.",
        "",
    ]

    if canary_hits:
        # First thing on the page, above the scores. Buried at the bottom it is
        # the one finding here that can be missed, and it is the one that must
        # not be. The marker itself is never printed: a string quoted into a
        # report is a string that can reach a student.
        names = ", ".join(roster.get(q.student, {}).get("name", q.student)
                          for q in canary_hits)
        out = out[:3] + [
            "",
            "> ## AI USE MARKER FOUND",
            ">",
            f"> **{len(canary_hits)} submission(s) carry the marker for this "
            f"lab.** They were graded like any other and their ratings are in "
            f"the distribution below. The marker was never sent to a model.",
            ">",
            f"> {names}",
            ">",
            "> Do not mention the marker in feedback, and do not quote it "
            "anywhere a student could read it.",
            "",
        ] + out[3:]

    by_criterion: dict[str, Counter] = defaultdict(Counter)
    exemplars: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in graded:
        for v in r.verdicts:
            by_criterion[v.criterion][v.rating] += 1
            if v.exemplary and v.evidence:
                exemplars[v.criterion].append((r.student, v.evidence[0]))

    out += ["## Where the class landed", ""]
    trouble: list[tuple[str, float]] = []
    distribution = []
    for c in card.criteria:
        counts = by_criterion.get(c.name, Counter())
        total = sum(counts.values()) or 1
        pct = counts["Missing"] / total
        if pct >= 0.4:
            trouble.append((c.name, pct))
        distribution.append([c.name, counts["Complete"], counts["Acceptable"],
                             counts["Missing"], f"{pct:.0%}"])
    out.append(table(["Criterion", "Complete", "Acceptable", "Missing", "Missing %"],
                     distribution))
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

    sims = [(x.similarity["score"], x.similarity.get("state"), x.student, x)
            for x in graded if x.similarity]
    if sims:
        sims.sort(reverse=True)
        import statistics
        scores = [s[0] for s in sims]
        out += ["## Originality reports", "",
                f"{len(sims)} of {len(graded)} carry a Canvas originality score. "
                f"Median {statistics.median(scores):.0f}%, range "
                f"{min(scores):.0f}% to {max(scores):.0f}%.", "",
                "**Read these against the class, not against zero.** A lab "
                "report is structurally high similarity: every student runs the "
                "same commands from the same handout on identical "
                "infrastructure, so the commands, the handout wording and the "
                "software banners all match. What is worth looking at is a "
                "score well above the class median, similarity in the analysis "
                "prose rather than in command output, and any two students "
                "sharing an address allocation, since every allocation is "
                "unique.", ""]
        rows = []
        for score, state, student, res in sims:
            name = roster.get(student, {}).get("name", student)
            note = "" if state in ("scored", "acceptable", None) else str(state)
            rows.append([name, f"{score:.0f}%", f"{res.awarded} of {res.possible}",
                         note])
        out.append(table(["Student", "Similarity", "Score", "Turnitin state"], rows))
        out.append("")
        failed = [s for s in sims if s[1] not in ("scored", "acceptable", None)]
        if failed:
            out.append(
                f"{len(failed)} report(s) did not finish processing. A state of "
                f"`failure` means no report was generated, which is not a low "
                f"score and must not be read as one.")
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

    unread = [r for r in graded if r.images_unread]
    if unread:
        out.append("### Images the grade never saw")
        out.append("")
        out.append(
            "These reports carry images past the card's `max_images` cap. The "
            "vision pass recorded them and did not read them, so no bullet "
            "could be satisfied from them. A high miss rate on a criterion "
            "whose evidence is visual means the cap before it means the class."
        )
        out.append("")
        for r in sorted(unread, key=lambda r: -r.images_unread):
            out.append(f"- {r.student}: {r.images_unread} of "
                       f"{sum(r.image_kinds.values())} image(s) unread")
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

    if canary_hits:
        out += ["## AI use marker", "",
                "Graded like any other submission. The marker was never sent "
                "to a model, and the student's own sheet says nothing about it "
                "beyond a note addressed to you.", ""]
        for q in canary_hits:
            out.append(f"- {q.student}")
        out.append("")

    return "\n".join(out)
