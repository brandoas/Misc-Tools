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

import re
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
    generic_hostnames: int = 0


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


@check("single_report_file")
def single_report_file(f: Facts) -> CheckResult:
    """One report, in either accepted format.

    For deliverables that accept both. ITS 4750 Lab 1 was posted allowing pdf
    and docx and every submission came in as PDF, so a docx only check would
    have failed all ten. The format tightens to docx only later in the term,
    and that is what single_docx is for.
    """
    ext = f.source.rsplit(".", 1)[-1].lower() if "." in f.source else ""
    if ext not in ("docx", "docm", "pdf"):
        return CheckResult(False, f"submitted as .{ext or 'unknown'}")
    if f.file_count > 1:
        return CheckResult(False, f"{f.file_count} files submitted, not one")
    return CheckResult(True, f"one report file ({f.source})")


#: Hostnames that are the image default or a handout placeholder, never a
#: student's own. Observed in ITS 4750 Lab 1: `itsclass@its-vyos-x` appears 173
#: times across 9 of 10 reports, because the stock VyOS image ships with that
#: name and nobody changed it.
#:
#: This matters beyond tidiness. The prompt is the only thing tying a block of
#: output to the machine that produced it, and with five near identical routers
#: in the lab, output from `its-vyos-x` cannot be attributed to any of them. It
#: is also the cheapest check on whether the work was done on the student's own
#: assigned host, since every student's hostname is unique.
#:
#: Add new placeholders here rather than to a card; they are a property of the
#: images and handouts, not of a deliverable.
#: No Windows defaults here. Brandon, 2026-10-02: a Windows terminal prompt is
#: `C:\Users\Student>` and carries no hostname at all, so DESKTOP-xxxxxxx and
#: WIN-xxxxxxxxxxx can never appear in one. Nor are Ubuntu-GUI or Ubuntu-CLI-1
#: listed: those are the topology object names, so a prompt showing one is
#: probably correct.
#:
#: Matched only inside a SHELL PROMPT, never in prose. "Ubuntu-GUI" is the
#: legitimate object name in these topologies and appears all over a correct
#: report; "itsclass@ubuntu:~$" is the image default nobody renamed. A pattern
#: that cannot tell those apart flags every student, which is the same as
#: flagging none.
#: Shape of a hostname sitting in a shell prompt. The NAMES come from the card.
#:
#: That split is the point. Which hostnames are "the default" is a property of
#: the images a cohort was handed, and those change whenever an image is
#: re-minted, so they belong with the card that names its cohort rather than in
#: this file. It is also what lets another course use Clerk without editing it.
#:
#: Matched only inside a prompt, never in prose: "Ubuntu-GUI" is the legitimate
#: object name in these topologies and appears all over a correct report, where
#: "itsclass@ubuntu:~$" is an image default nobody renamed. A pattern that
#: cannot tell those apart flags every student, which is the same as flagging
#: none.
#:
#: No Windows defaults, ever. A Windows terminal prompt shows a path and no
#: hostname at all, so DESKTOP-xxxxxxx can never appear in one.
PROMPT_HOST = r"[\w.-]+@({names})(?=[\s:~$#)\].,]|$)"

#: Used only when a card names none. Stock images any course would see, with
#: nothing local to one institution.
STOCK_DEFAULTS = ("ubuntu", "debian", "vyos", "localhost", "localhost.localdomain")


def generic_hostname_re(names=None):
    """Build the prompt matcher for one card's declared image defaults.

    A name may end in `*` to match a suffix, so a card can say `its-uc-*` and
    catch `its-uc-xxx` without knowing what the placeholder looks like.
    """
    chosen = [n for n in (names or []) if n] or list(STOCK_DEFAULTS)
    alts = "|".join(re.escape(n).replace(r"\*", r"[\w-]*") for n in chosen)
    return re.compile(PROMPT_HOST.format(names=alts), re.I | re.M)


@check("no_generic_hostnames")
def no_generic_hostnames(f: Facts) -> CheckResult:
    """The student's own hostname, not the image default or a placeholder."""
    if f.generic_hostnames:
        return CheckResult(
            False,
            f"a generic hostname appears {f.generic_hostnames} time(s); output "
            f"cannot be attributed to a specific device")
    return CheckResult(True, "no generic or placeholder hostnames")


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
