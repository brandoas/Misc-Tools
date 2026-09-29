"""Canary detection. Runs before any prompt is built, and never involves a model.

Some labs carry a hidden marker in the README that only surfaces if a student
pasted the lab into a chatbot. The course rule is: do not grade it, do not
mention it in feedback, send it to Brandon.

That rule is implemented here and nowhere else, for one reason. A model told not
to mention a string will eventually mention it, and the place it will surface is
a rubric comment a student reads. So a submission carrying the marker is
quarantined before a prompt exists, the marker text never enters a prompt or a
verdict, and the cohort report names the student and nothing else.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass
class Quarantine:
    student: str
    reason: str = "canary"


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
    canary simply never quarantines.
    """
    if not marker:
        return False
    return normalise(marker) in normalise(report_text)


def screen(marker: str | None, submissions: dict[str, str]) -> list[Quarantine]:
    """Screen a whole cohort. submissions maps student to extracted report text."""
    return [
        Quarantine(student=student)
        for student, text in sorted(submissions.items())
        if found(marker, text)
    ]
