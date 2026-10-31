"""Markdown helpers for the files a human reads.

The review sheets and lab notes are read in an editor with markdownlint on, so
the tables they carry should pass it. Unpadded tables (`|---|---|`) trip MD060
and, more to the point, are hard to read as source: the columns do not line up,
so a criterion and its numbers drift apart on a wide table.

This pads every cell to its column width and right aligns numeric columns, which
satisfies MD055 (leading and trailing pipes), MD056 (consistent column count)
and MD060 (consistent column style), and makes the source readable without
rendering it.
"""

from __future__ import annotations

import re

#: A cell that should be right aligned: integers, percentages, scores like
#: "9 of 10", and decimals. Text columns stay left aligned.
NUMERIC = re.compile(r"^\*{0,2}-?\d[\d,.]*\s*(%|of\s+\d+|pts?|min)?\*{0,2}$")


def table(headers: list[str], rows: list[list[object]]) -> str:
    """Render a padded, lint clean Markdown table.

    Cells are stringified, so callers can pass numbers directly. A row with the
    wrong number of cells is padded or truncated rather than raising, because a
    malformed table in a review sheet should not take down a grading run.
    """
    width = len(headers)
    body = []
    for row in rows:
        cells = [_clean(c) for c in row][:width]
        cells += [""] * (width - len(cells))
        body.append(cells)

    heads = [_clean(h) for h in headers]
    # A column is numeric when every non empty cell in it looks numeric.
    right = []
    for i in range(width):
        values = [r[i] for r in body if r[i].strip()]
        right.append(bool(values) and all(NUMERIC.match(v) for v in values))

    widths = []
    for i in range(width):
        # Minimum three so the separator can carry an alignment colon.
        widths.append(max(3, len(heads[i]), *(len(r[i]) for r in body)) if body
                      else max(3, len(heads[i])))

    def line(cells: list[str]) -> str:
        out = []
        for i, c in enumerate(cells):
            out.append(c.rjust(widths[i]) if right[i] else c.ljust(widths[i]))
        return "| " + " | ".join(out) + " |"

    sep = []
    for i in range(width):
        sep.append("-" * (widths[i] - 1) + ":" if right[i] else "-" * widths[i])

    return "\n".join([line(heads), "| " + " | ".join(sep) + " |",
                      *(line(r) for r in body)])


def _clean(value: object) -> str:
    """Stringify a cell and neutralise anything that would break the table.

    A pipe inside a cell silently splits it into two columns, which markdownlint
    then reports as a column count error on a row the author never touched. A
    newline does worse. Both turn up in student text, which is where most of
    these cells come from.
    """
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()
