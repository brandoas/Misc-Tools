"""Canary detection. Runs before any prompt is built, and never involves a model.

Some labs carry a hidden marker in the README that only surfaces if a student
pasted the lab into a chatbot. The course rule is: grade the work as normal, do
not mention the marker in feedback, and tell Brandon which submissions carried
it.

Notify, not quarantine. Brandon, 2026-10-23: the marker was always meant to
raise a flag rather than withhold a grade, because it is evidence about how a
report was written and not a finding about the work. Through 2026-10-22 the
callers of this module skipped a flagged submission entirely and produced no
rating at all for it, which is a penalty applied in code before a human had
read anything.

What stays in code is the part a model cannot be trusted with. A model told not
to mention a string will eventually mention it, and the place it would surface
is a rubric comment a student reads. So detection happens here and nowhere
else, the marker text never enters a prompt, a verdict or a comment, and the
flag reaches Brandon through the review sheet and the cohort report, which only
he reads.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass
class CanaryHit:
    """One submission carrying the marker. It is still graded like any other."""

    student: str
    reason: str = "canary"


#: The former name. Run directories written before 2026-10-23 hold a
#: `quarantine.json`, and the loader builds these from it, so the old word
#: survives on disk even though nothing is withheld any more.
Quarantine = CanaryHit


def normalise(text: str) -> str:
    """Fold the text so a marker survives a round trip through Word.

    Word will change straight quotes to curly ones, split a pasted string across
    runs, and rewrite spaces as non breaking. Comparing raw text misses all of
    that, so both sides are folded: unicode normalised, punctuation flattened,
    whitespace collapsed, and case dropped.
    """
    text = unicodedata.normalize("NFKD", text)
    text = (text.replace("‘", "'").replace("’", "'")
                .replace("“", '"').replace("”", '"')
                .replace("–", "-").replace("—", "-")
                .replace(" ", " ").replace("​", ""))
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def found(marker: str | None, report_text: str) -> bool:
    """Is the marker present in the report?

    Returns False for an empty marker rather than raising, so a lab with no
    canary simply never flags anything.
    """
    if not marker:
        return False
    return normalise(marker) in normalise(report_text)


def screen(marker: str | None, submissions: dict[str, str]) -> list[CanaryHit]:
    """Screen a whole cohort. submissions maps student to extracted report text.

    Screening only. Nothing here decides whether a submission gets graded.
    """
    return [
        CanaryHit(student=student)
        for student, text in sorted(submissions.items())
        if found(marker, text)
    ]
