"""Bullets the tool answers itself, because the model cannot see them.

Some rubric bullets are facts about the submission rather than about its
content. The container format is one: nothing inside a document says "I am a
Word document", so a judge reading extracted text can only report that it found
no evidence. On ITS 3100 D02 that cost **28 of 29 students** a point on "One
Word document", every one of whom had submitted a .docx, and the model went
further and asserted "The submission is not a Word document."

The monospace bullets fail the opposite way. "Terminal text as text" caught only
7 of 29, and a report with zero fixed width formatting anywhere scored 86,
because fluent prose about command output reads like evidence of command output.

Both facts are already measured during extraction and were sitting unused. A
check here answers the bullet deterministically, the bullet never reaches the
model, and the rating stops depending on whether the model could infer something
it was never shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Facts:
    """What the tool knows about a submission without reading its meaning."""
    student: str
    source: str = ""            # the submitted filename
    file_count: int = 1         # how many files the student attached
    monospace_ratio: float = 0.0
    char_count: int = 0
    image_count: int = 0
    terminal_images: int = 0
    wireshark_images: int = 0
    unformatted_terminal: int = 0


@dataclass
class CheckResult:
    satisfied: bool
    note: str
    #: A failure that zeroes the whole criterion rather than costing one bullet.
    #: Reserved for measurements where a failure means the requirement was not
    #: attempted at all, not that it was done badly.
    hard_fail: bool = False


Check = Callable[[Facts], CheckResult]
REGISTRY: dict[str, Check] = {}


def check(name: str):
    def register(fn: Check) -> Check:
        REGISTRY[name] = fn
        return fn
    return register


@check("single_docx")
def single_docx(f: Facts) -> CheckResult:
    """One Word document, which is what the assignment asks for."""
    ext = f.source.rsplit(".", 1)[-1].lower() if "." in f.source else ""
    if ext not in ("docx", "docm"):
        return CheckResult(False, f"submitted as .{ext or 'unknown'}, not a Word document")
    if f.file_count > 1:
        return CheckResult(False, f"{f.file_count} files submitted, not one")
    return CheckResult(True, f"one Word document ({f.source})")


@check("single_pdf")
def single_pdf(f: Facts) -> CheckResult:
    ext = f.source.rsplit(".", 1)[-1].lower() if "." in f.source else ""
    if ext != "pdf":
        return CheckResult(False, f"submitted as .{ext or 'unknown'}, not a PDF")
    if f.file_count > 1:
        return CheckResult(False, f"{f.file_count} files submitted, not one")
    return CheckResult(True, f"one PDF ({f.source})")


@check("monospace_present")
def monospace_present(f: Facts) -> CheckResult:
    """Terminal text set as text.

    Zero is the line that matters and it is not a judgement call: a report with
    no fixed width run anywhere did not paste its command output as text, whatever
    the prose claims. Brandon's rule, 2026-09-27: that scores zero on the element.

    Above zero this check passes and the model still judges whether the right
    things are in monospace. This catches the absolute failure, not the sloppy one.
    """
    if f.monospace_ratio <= 0.0:
        # Brandon, 2026-09-27: a full points deduction, not one bullet.
        #
        # Zero is categorically different from sloppy. A report with no fixed
        # width run anywhere did not paste command output as text at all, so
        # every other Report Standards bullet is being judged on prose about
        # evidence rather than on the evidence. Costing one point of ten made
        # that indistinguishable from a missing figure label.
        return CheckResult(False, "no fixed width text anywhere in the document",
                           hard_fail=True)
    return CheckResult(True, f"{f.monospace_ratio:.0%} of the text is fixed width")


@check("no_wireshark_screenshots")
def no_wireshark_screenshots(f: Facts) -> CheckResult:
    """Packet data as a picture of Wireshark.

    Wireshark output should never arrive as an image. The packet list is text,
    the detail tree is text, and a screenshot of either cannot be searched,
    quoted, or checked against the command that produced it. It is also the
    single most common way a report hides that the capture does not show what
    the student says it shows.

    Detected by colour rather than by content: the packet list colourises rows
    by protocol, so the image carries many tinted horizontal bands. A terminal,
    the other dense text screenshot in these reports, is uniformly dark or
    uniformly light. See extract.classify.
    """
    if f.wireshark_images:
        return CheckResult(
            False,
            f"{f.wireshark_images} Wireshark screenshot(s); packet data belongs "
            f"in the report as text")
    return CheckResult(True, "no Wireshark screenshots detected")


@check("terminal_text_formatted")
def terminal_text_formatted(f: Facts) -> CheckResult:
    """Command output set in a fixed width font, wherever it appears.

    Stricter than monospace_present, and catches a different failure. A report
    can be 60 percent fixed width and still have its ping output in Calibri,
    which the ratio alone cannot see.

    Proportional type does not merely look wrong, it destroys the data. Seen in
    the Fall 2026 class, an `ip route` line reflowed into

        route4 132.235.2 itsclass@its-uc-xxx:~$
        itsclass@its-uc-xxx:~$ 04.192/26 metric 100

    with 132.235.204.192/26 split across two lines and a prompt pushed through
    the middle. The address is no longer readable and no longer checkable.

    Three or more such paragraphs, rather than one, so a single prompt quoted
    inline in a sentence does not trip it.
    """
    if f.unformatted_terminal >= 3:
        return CheckResult(
            False,
            f"{f.unformatted_terminal} block(s) of terminal output are set in a "
            f"proportional font; column alignment is lost",
            hard_fail=f.monospace_ratio <= 0.0)
    return CheckResult(True, "terminal output is in fixed width type")


@check("no_terminal_screenshots")
def no_terminal_screenshots(f: Facts) -> CheckResult:
    """Command output as text rather than as pictures of text."""
    if f.terminal_images:
        return CheckResult(
            False, f"{f.terminal_images} image(s) look like terminal screenshots")
    return CheckResult(True, "no terminal screenshots detected")


def run(name: str, facts: Facts) -> CheckResult:
    fn = REGISTRY.get(name)
    if fn is None:
        raise KeyError(f"unknown check {name!r}. Known: {', '.join(sorted(REGISTRY))}")
    return fn(facts)


def known() -> list[str]:
    return sorted(REGISTRY)
