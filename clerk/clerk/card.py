"""Parse and lint a grader card.

A card is the grading instrument for one deliverable: front matter plus one
section per Canvas rubric criterion, each carrying an Evidence list and a
Critique list. The format is specified in INPUT-SPEC.md, which is normative.

Nothing here judges anything. This module only turns a hand written Markdown
file into objects, and refuses the ones that are malformed or unsigned.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
CRITERION_RE = re.compile(r"^##\s+(?P<name>.+?)\s*\((?P<points>\d+)\)\s*$", re.M)
TASKS_RE = re.compile(r"^tasks:\s*\[(?P<body>[^\]]*)\]\s*$", re.M)
OBJECTIVE_RE = re.compile(r"^objective:\s*(?P<body>.+?)\s*$", re.M)
CHECK_RE = re.compile(r"^check\s+(?P<index>\d+):\s*(?P<name>[a-z_]+)\s*$", re.M)
SUBHEAD_RE = re.compile(r"^###\s+(?P<name>.+?)\s*$", re.M)
BULLET_RE = re.compile(r"^-\s+(?P<text>.+?)\s*$", re.M)

REQUIRED_KEYS = (
    "course", "deliverable", "title", "canvas_rubric",
    "points", "ratings", "canary",
)


class CardError(Exception):
    """A card that cannot be used. Always carries a fixable message."""


@dataclass
class Criterion:
    name: str
    points: int
    #: The lab's own Objective line for this task, copied from the handout.
    #: This is the standard the student was given, so it is the standard the
    #: judge grades to. The Evidence bullets operationalise it; they do not
    #: replace it, and a bullet that does not serve the objective does not
    #: belong on the card.
    objective: str = ""
    tasks: list[int] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    critique: list[str] = field(default_factory=list)
    #: Evidence bullets the tool answers itself, {1 based index: check name}.
    #: These never reach the model, because they are facts about the submission
    #: rather than about its content and a judge reading extracted text cannot
    #: see them. See checks.py for why this exists.
    checks: dict[int, str] = field(default_factory=dict)

    @property
    def acceptable_points(self) -> int:
        """Acceptable is full minus one, floored at zero for a 1 point row."""
        return max(self.points - 1, 0)


@dataclass
class Card:
    path: Path
    meta: dict
    criteria: list[Criterion]

    @property
    def course(self) -> str:
        return str(self.meta["course"])

    @property
    def deliverable(self) -> str:
        return str(self.meta["deliverable"])

    @property
    def slug(self) -> str:
        return f"{self.course.replace('ITS-', '')}-d{self.deliverable}"

    @property
    def canary(self) -> str | None:
        value = self.meta.get("canary")
        return value or None

    @property
    def total_points(self) -> int:
        return sum(c.points for c in self.criteria)

    def criterion(self, name: str) -> Criterion:
        for c in self.criteria:
            if c.name == name:
                return c
        raise CardError(f"no criterion named {name!r} in {self.path.name}")


def load(path: str | Path) -> Card:
    """Read a card file into a Card. Raises CardError on anything malformed.

    This does not check the review signature. Grading paths call
    require_reviewed() as well; lint reports the signature as one finding among
    others so an author can see every problem in one pass.
    """
    path = Path(path)
    if not path.is_file():
        raise CardError(f"no card at {path}")
    text = path.read_text(encoding="utf-8")

    m = FRONT_MATTER_RE.match(text)
    if not m:
        raise CardError(f"{path.name} has no YAML front matter")
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise CardError(f"{path.name} front matter is not valid YAML: {e}") from e
    if not isinstance(meta, dict):
        raise CardError(f"{path.name} front matter is not a mapping")

    body = text[m.end():]
    criteria = _parse_criteria(body, path)
    if not criteria:
        raise CardError(f"{path.name} declares no criteria")
    return Card(path=path, meta=meta, criteria=criteria)


def _parse_criteria(body: str, path: Path) -> list[Criterion]:
    """Split the body on '## Name (points)' headings and parse each block."""
    marks = list(CRITERION_RE.finditer(body))
    out: list[Criterion] = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        block = body[mark.end():end]
        obj = OBJECTIVE_RE.search(block)
        crit = Criterion(
            name=mark.group("name").strip(),
            points=int(mark.group("points")),
            objective=obj.group("body").strip() if obj else "",
            tasks=_parse_tasks(block, mark.group("name"), path),
        )
        crit.checks = {int(m.group("index")): m.group("name")
                       for m in CHECK_RE.finditer(block)}
        crit.evidence = _bullets_under(block, "Evidence")
        crit.critique = _bullets_under(block, "Critique")
        out.append(crit)
    return out


def _parse_tasks(block: str, name: str, path: Path) -> list[int]:
    m = TASKS_RE.search(block)
    if not m:
        return []
    raw = m.group("body").strip()
    if not raw:
        return []
    try:
        return [int(p.strip()) for p in raw.split(",") if p.strip()]
    except ValueError as e:
        raise CardError(
            f"{path.name}: criterion {name!r} has a tasks list that is not "
            f"all integers: [{raw}]"
        ) from e


def _bullets_under(block: str, heading: str) -> list[str]:
    """Collect '- ' bullets under a '### heading' until the next '###'."""
    heads = list(SUBHEAD_RE.finditer(block))
    for i, h in enumerate(heads):
        if h.group("name").strip().lower() != heading.lower():
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(block)
        return [b.group("text") for b in BULLET_RE.finditer(block[h.end():end])]
    return []


def signature_is_current(card: Card) -> tuple[bool, str]:
    """Is the human review signature present and newer than the file itself?

    The gate exists because the grading guides these cards derive from were
    largely machine drafted and carry real errors. Editing a card invalidates
    the signature, so a change cannot reach a student grade without someone
    reading it again.

    Compared against the file mtime by date, not timestamp, because a signature
    is a date and an author cannot sign a file at a finer resolution than the
    day they read it.
    """
    who = card.meta.get("reviewed_by")
    when = card.meta.get("reviewed")
    if not who or not when:
        return False, "card is unsigned: set reviewed_by and reviewed once a human has read it"
    if isinstance(when, str):
        try:
            when = _dt.date.fromisoformat(when.strip())
        except ValueError:
            return False, f"reviewed is not an ISO date: {when!r}"
    if isinstance(when, _dt.datetime):
        when = when.date()
    if not isinstance(when, _dt.date):
        return False, f"reviewed is not a date: {when!r}"

    mtime = _dt.date.fromtimestamp(os.path.getmtime(card.path))
    if when < mtime:
        return False, (
            f"signature is stale: reviewed {when.isoformat()} but the file was "
            f"modified {mtime.isoformat()}. A human signs the card after editing it."
        )
    return True, f"signed by {who} on {when.isoformat()}"


def require_reviewed(card: Card) -> None:
    ok, why = signature_is_current(card)
    if not ok:
        raise CardError(f"{card.path.name}: {why}")


def lint(card: Card, lab=None) -> list[str]:
    """Return a list of findings. Empty means the card is well formed.

    Well formed is not the same as correct. Only a human decides whether the
    Evidence bullets actually measure the thing the criterion names.
    """
    findings: list[str] = []

    for key in REQUIRED_KEYS:
        if key not in card.meta:
            findings.append(f"front matter is missing {key!r}")

    declared = card.meta.get("points")
    if isinstance(declared, int) and declared != card.total_points:
        findings.append(
            f"points mismatch: front matter says {declared}, criteria sum to "
            f"{card.total_points}. The Canvas rubric is the authority."
        )

    names = [c.name for c in card.criteria]
    for dupe in {n for n in names if names.count(n) > 1}:
        findings.append(f"duplicate criterion name {dupe!r}")

    for c in card.criteria:
        if not c.objective:
            findings.append(
                f"criterion {c.name!r} has no objective. Copy the handout's "
                f"IMPORTANT Objective line for this task. It is the standard "
                f"the student was given, so it is what they are graded against."
            )
        if not c.evidence:
            findings.append(f"criterion {c.name!r} has no Evidence bullets")
        if not c.critique:
            findings.append(f"criterion {c.name!r} has no Critique bullets")
        if len(c.evidence) > 12:
            findings.append(
                f"criterion {c.name!r} has {len(c.evidence)} Evidence bullets. "
                f"Over about eight, consider splitting the criterion."
            )
        for bullet in c.evidence:
            if _is_unobservable(bullet):
                findings.append(
                    f"criterion {c.name!r}: Evidence bullet is not observable "
                    f"from the report: {bullet!r}"
                )
        from .checks import known as _known_checks
        for idx, name in c.checks.items():
            if not 1 <= idx <= len(c.evidence):
                findings.append(
                    f"criterion {c.name!r} has 'check {idx}: {name}' but only "
                    f"{len(c.evidence)} Evidence bullets")
            if name not in _known_checks():
                findings.append(
                    f"criterion {c.name!r} names unknown check {name!r}. "
                    f"Known: {', '.join(_known_checks())}")
        if card.canary and card.canary in " ".join(c.evidence + c.critique):
            findings.append(
                f"criterion {c.name!r} quotes the canary marker. Canaries are "
                f"handled in code only, never in a bullet."
            )

    if lab is not None:
        known = set(lab.task_numbers())
        for c in card.criteria:
            for t in c.tasks:
                if t not in known:
                    findings.append(
                        f"criterion {c.name!r} references task {t}, which is not "
                        f"in {lab.path.name}"
                    )
            findings.extend(_objective_findings(c, lab))

    ok, why = signature_is_current(card)
    if not ok:
        findings.append(why)

    return findings


def _objective_findings(c: Criterion, lab) -> list[str]:
    """Check the card's objective against the handout's own Objective line.

    A criterion whose objective does not appear in the handout is grading
    students against something they were never told to do. That is the defect
    this check exists for: ITS 3100 Deliverable 01 shipped with a grader card
    criterion for a question the handout never asked.
    """
    out: list[str] = []
    if not c.objective or not c.tasks:
        return out
    for number in c.tasks:
        task = lab.task(number)
        if task is None:
            continue
        stated = task.objective
        if not stated:
            out.append(
                f"criterion {c.name!r} points at task {number}, which carries no "
                f"Objective line in {lab.path.name}. Either the handout is "
                f"missing its IMPORTANT prompt, or this criterion grades "
                f"something the student was not asked for."
            )
            continue
        if _similar(c.objective, stated):
            return []
    if len(c.tasks) == 1:
        out.append(
            f"criterion {c.name!r} objective does not match the Objective line "
            f"on task {c.tasks[0]} in {lab.path.name}. The handout wins."
        )
    return out


def _similar(a: str, b: str, threshold: float = 0.75) -> bool:
    import difflib
    norm = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio() >= threshold


UNOBSERVABLE = (
    "understands", "understanding", "demonstrates knowledge",
    "shows comprehension", "grasps", "appreciates", "is aware",
)


def _is_unobservable(bullet: str) -> bool:
    """Flag bullets that ask about a mental state rather than about the report.

    A grader can only see what is on the page. 'Student understands SLAAC' is
    not gradeable and invites the model to reward fluent prose, which is this
    tool's main failure mode.
    """
    low = bullet.lower()
    return any(phrase in low for phrase in UNOBSERVABLE)
