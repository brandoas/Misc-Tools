"""Judge one report against one criterion.

The model does not produce a grade. It produces findings: which Evidence bullets
it can support with a verbatim quote from the report, and which it cannot. The
rating follows from those findings by a rule in code, so two students with the
same findings get the same rating no matter what the model felt about their
prose.

That split is the whole design. It is also what makes a rating answerable when a
student challenges it, because the answer is a list of quotes from their own
report rather than an assertion about quality.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from . import checks
from .card import Card, Criterion
from .lab import Lab

SYSTEM = """\
You are grading one criterion of a student network lab report for an Ohio \
University ECT course. You are precise, literal, and you do not give credit for \
fluent writing.

You are given the objective the student was told to achieve, the task they were \
assigned, a checklist of evidence, and the student's report. The objective is \
the standard. The checklist is how it is measured. For each checklist item you \
decide whether the report contains the evidence, and you support every yes with \
a quote copied character for character out of the report.

Rules you follow without exception:

1. A quote must appear verbatim in the report. Do not paraphrase, do not tidy \
spacing, do not correct a typo. Quotes are checked mechanically and a quote that \
cannot be found voids your whole answer.
2. Evidence means data. A student claiming they configured something is not \
evidence that they did. Command output, an address, a capture, a screenshot \
transcription, or a specific technical statement is evidence.
3. Analysis is not restatement. If a checklist item asks the student to explain \
or identify something, a paste of the configuration or the raw output does not \
satisfy it, however long it is.
4. Well written prose that contains no data satisfies nothing. This is the \
failure you are most likely to make, so check yourself for it.
5. Judge only the checklist you were given. Work belonging to another part of \
the report is not your concern.
6. Images in the report appear as transcriptions inside [IMAGE-NN] blocks. Treat \
a transcription as the student's data, and quote from it the same way.

Return only a JSON object matching the schema.\
"""

PROMPT = """\
# The student report

{report}

# The task this criterion covers

{task_context}

# Criterion: {criterion} ({points} points)

## What the student was told to achieve

{objective}

That sentence is the standard. It is the objective printed in the student's own
handout, so it is what they were asked for, and the checklist below is only how
it gets measured. Where the two ever pull apart, the objective wins.

## Evidence checklist

{evidence}

## Known failure modes for this criterion

{critique}

For each numbered checklist item, decide satisfied true or false, and give a \
verbatim supporting quote from the report when true. Then write one sentence of \
feedback naming what is missing, for the student to read. Do not mention the \
checklist or the rubric in that sentence.\
"""


class Finding(BaseModel):
    item: int = Field(description="1 based index into the evidence checklist")
    satisfied: bool
    quote: str = Field(default="", description="verbatim from the report, empty if not satisfied")


class Response(BaseModel):
    findings: list[Finding]
    comment: str = Field(default="", description="one sentence of feedback naming what is missing")
    exemplary: bool = Field(
        default=False,
        description="true only if this work is worth showing a future class as an example",
    )


@dataclass
class Verdict:
    criterion: str
    points: int
    rating: str
    awarded: int
    evidence: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    comment: str = ""
    confidence: str = "high"
    exemplary: bool = False
    voided: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "criterion": self.criterion,
            "points": self.points,
            "rating": self.rating,
            "awarded": self.awarded,
            "evidence": self.evidence,
            "missing": self.missing,
            "comment": self.comment,
            "confidence": self.confidence,
            "exemplary": self.exemplary,
            "voided": self.voided,
        }


def build_prompt(card: Card, lab: Lab, criterion: Criterion, report: str) -> str:
    """Assemble the user prompt.

    Ordering is load bearing. The report goes first because it is the same for
    every criterion of a given student, and Ollama reuses the KV cache for a
    shared prompt prefix. Judging one student's criteria consecutively then
    prefills the report once rather than once per criterion, which on an eight
    criterion card is most of the wall clock.
    """
    # Machine checked bullets are left out of the checklist entirely rather than
    # sent and then overridden. Asking the model about a fact it cannot see
    # produces a confident wrong answer: on D02 it told 28 of 29 students "The
    # submission is not a Word document" about their .docx files. The item
    # numbers are kept aligned with the card, so findings still map back.
    evidence = "\n".join(f"{i}. {b}" for i, b in enumerate(criterion.evidence, 1)
                         if i not in criterion.checks)
    critique = "\n".join(f"- {b}" for b in criterion.critique) or "(none recorded)"
    return PROMPT.format(
        report=report,
        task_context=lab.context_for(criterion.tasks),
        criterion=criterion.name,
        points=criterion.points,
        objective=criterion.objective or "(no objective recorded for this criterion)",
        evidence=evidence,
        critique=critique,
    )


#: Quote characters a model wraps its answer in, straight and curly.
_WRAPPERS = "\"'“”‘’«»`"


def _unwrap(text: str) -> str:
    """Strip the decoration a model puts around a quote it is reporting.

    Measured on the first real run against ai-01: eight of the eleven verbatim
    check failures were this and nothing else. The model returns
    '"set interfaces ethernet eth0 dhcpv6-options pd 0 ..."' with literal
    quotation marks it added itself, the characters are not in the report, and a
    correct finding gets voided as fabricated.

    That is the worst possible direction for this check to fail in. A false
    fabrication flag trains the reader to ignore the flag, which is what makes
    the real ones worthless.
    """
    text = text.strip()
    # Fenced blocks, which the model copies along with the evidence.
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    # Blockquote markers on every line.
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    # Wrapping quotes, possibly several deep.
    prev = None
    while prev != text:
        prev = text
        text = text.strip()
        if len(text) >= 2 and text[0] in _WRAPPERS and text[-1] in _WRAPPERS:
            text = text[1:-1]
    return text.strip()


def _normalise(text: str) -> str:
    """Fold whitespace so a quote survives the trip through Word and Markdown."""
    return re.sub(r"\s+", " ", text).strip().casefold()


#: Outcomes of the verbatim check. FOUND counts towards the rating; TOO_SHORT
#: does not count but is not evidence of fabrication either; NOT_FOUND is the
#: one that voids a criterion and calls a human.
FOUND, TOO_SHORT, NOT_FOUND = "found", "too_short", "not_found"

#: Below this a quote proves nothing and matches by accident. '[IMAGE-01]' is
#: ten characters and was being reported as fabricated on the first real run,
#: which is a different and much more serious accusation than 'too short'.
MIN_QUOTE_CHARS = 12


def check_quote(quote: str, report: str, *, threshold: float = 0.92) -> str:
    """Classify a quote: FOUND, TOO_SHORT, or NOT_FOUND.

    A quote may be stitched from several places in the report, and usually is.
    Asked whether the SLAAC and DHCPv6 addresses are distinguished from each
    other, the model returns the sentence defining one and the sentence defining
    the other, because that is where the student put them. Neither the student
    nor the model did anything wrong, and a single contiguous window check
    rejects it.

    So: try the whole string first, then fall back to verifying each fragment
    independently. **Every** fragment above the length floor has to be found,
    which is what keeps the anti fabrication property: a real sentence stitched
    to an invented one still fails.
    """
    q = _normalise(_unwrap(quote))
    if len(q) < MIN_QUOTE_CHARS:
        return TOO_SHORT
    hay = _normalise(report)
    if _appears(q, hay, threshold):
        return FOUND

    fragments = [f for f in _fragments(_unwrap(quote))
                 if len(_normalise(f)) >= MIN_QUOTE_CHARS]
    if len(fragments) < 2:
        return NOT_FOUND
    if all(_appears(_normalise(f), hay, threshold) for f in fragments):
        return FOUND
    return NOT_FOUND


def _fragments(quote: str) -> list[str]:
    """Split a stitched quote into the pieces it was assembled from.

    Sentence ends and explicit elisions, which is how a model joins passages it
    took from different places.
    """
    parts = re.split(r"(?<=[.!?])\s+|\s*\.\.\.\s*|\s*…\s*|\n{2,}", quote)
    return [p.strip() for p in parts if p.strip()]


def verify_quote(quote: str, report: str, *, threshold: float = 0.92) -> bool:
    """Is this quote actually in the report?

    Exact match after whitespace folding, then a similarity check against the
    best matching window of the same length. The fuzzy step is there because
    Word mangles quotation marks and dashes on the way in, not to forgive
    paraphrase: at 0.92 a reworded sentence does not pass, while a curly
    apostrophe does.
    """
    return check_quote(quote, report, threshold=threshold) == FOUND


def _appears(q: str, hay: str, threshold: float) -> bool:
    """Exact match after folding, then a sliding similarity check.

    The fuzzy pass forgives what Word and PDF extraction do to a correct quote
    (curly punctuation, reflowed spacing), not paraphrase: at 0.92 a reworded
    sentence still fails.
    """
    if q in hay:
        return True
    window = len(q)
    step = max(window // 4, 1)
    for i in range(0, max(len(hay) - window, 0) + 1, step):
        if difflib.SequenceMatcher(None, q, hay[i:i + window]).ratio() >= threshold:
            return True
    return False


def rate(criterion: Criterion, satisfied: int, total: int) -> str:
    """Findings to rating, in code.

    Complete needs every checklist item. Acceptable means the work is there but
    incomplete, which is what the course rubric's full minus one with a comment
    is for. Missing means absent or unsupported by data.

    The one third floor for Missing is the judgement call in this function. Below
    it there is not enough on the page to call the criterion attempted, and the
    course rule is that a criterion claimed with no data behind it scores zero
    rather than nearly full.
    """
    if total == 0:
        return "Missing"
    if satisfied == total:
        return "Complete"
    if satisfied >= max(1, round(total / 3)):
        return "Acceptable"
    return "Missing"


def build_verdict(criterion: Criterion, response: Response, report: str,
                  facts: "checks.Facts | None" = None) -> Verdict:
    """Turn a model response into a rating, discarding anything unsupported."""
    facts = facts or checks.Facts(student="")
    evidence: list[str] = []
    missing: list[str] = []
    voided: list[str] = []
    hard_failed: list[str] = []
    satisfied = 0

    by_item = {f.item: f for f in response.findings}
    for i, bullet in enumerate(criterion.evidence, 1):
        if i in criterion.checks:
            result = checks.run(criterion.checks[i], facts)
            if result.satisfied:
                satisfied += 1
                evidence.append(f"[checked] {result.note}")
            else:
                missing.append(f"{bullet} ({result.note})")
                if result.hard_fail:
                    hard_failed.append(result.note)
            continue
        finding = by_item.get(i)
        if finding is None:
            missing.append(bullet)
            continue
        if not finding.satisfied:
            missing.append(bullet)
            continue
        if not finding.quote.strip():
            # Claimed satisfied with nothing behind it. By the course rule that
            # is not evidence, so it does not count.
            missing.append(bullet)
            voided.append(f"item {i} claimed satisfied with no quote")
            continue
        outcome = check_quote(finding.quote, report)
        if outcome is TOO_SHORT or outcome == TOO_SHORT:
            # Not evidence, but not a fabrication either. It does not count
            # towards the rating and it does not call a human, because crying
            # fabrication over a ten character fragment is how a flag stops
            # meaning anything.
            missing.append(bullet)
            continue
        if outcome == NOT_FOUND:
            # The model asserted evidence that is not in the report. This is the
            # failure that would make a grade indefensible, so the item is not
            # credited and the whole criterion is flagged for a human.
            missing.append(bullet)
            voided.append(f"item {i} quote not found in report: {finding.quote[:80]!r}")
            continue
        satisfied += 1
        evidence.append(_unwrap(finding.quote))

    rating = rate(criterion, satisfied, len(criterion.evidence))
    if hard_failed:
        # A hard failing check means the requirement was not attempted, so the
        # criterion scores zero however well the rest of it reads.
        rating = "Missing"
    awarded = {
        "Complete": criterion.points,
        "Acceptable": criterion.acceptable_points,
        "Missing": 0,
    }[rating]

    return Verdict(
        criterion=criterion.name,
        points=criterion.points,
        rating=rating,
        awarded=awarded,
        evidence=evidence,
        missing=missing,
        comment="; ".join(hard_failed) if hard_failed else response.comment.strip(),
        confidence="low" if voided else "high",
        exemplary=bool(response.exemplary) and rating == "Complete",
        voided=voided,
    )


async def judge_criterion(engine, card: Card, lab: Lab, criterion: Criterion,
                          report: str, facts: "checks.Facts | None" = None) -> Verdict:
    unchecked = [i for i in range(1, len(criterion.evidence) + 1)
                 if i not in criterion.checks]
    if not unchecked:
        # Every bullet is machine checkable, so there is nothing to ask.
        return build_verdict(criterion, Response(findings=[]), report, facts)
    response = await engine.ask(
        SYSTEM, build_prompt(card, lab, criterion, report), Response
    )
    return build_verdict(criterion, response, report, facts)
