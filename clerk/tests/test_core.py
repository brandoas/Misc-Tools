"""Tests for the parts that decide a grade without a model in the loop.

Everything here is offline. Nothing calls an inference host, nothing reads a
real submission. The model's job is to find evidence; these functions turn
findings into a rating, and they are what has to be right for a grade to be
defensible.

Each test names the failure it guards against, and each was checked by breaking
the code and confirming the test caught it.

    python -m pytest tests -q
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from clerk import canaries
from clerk import card as card_mod
from clerk.card import Criterion
from clerk.judge import Response, Finding, build_verdict, rate, verify_quote

CARDS = Path(__file__).parent.parent / "cards"
LABS = Path(__file__).parent.parent / "labs"


# --- the rating rule ---------------------------------------------------------

def crit(points=15, n=6):
    return Criterion(name="X", points=points,
                     evidence=[f"bullet {i}" for i in range(1, n + 1)],
                     critique=["some failure"])


def test_complete_requires_every_bullet():
    """Five of six is not Complete.

    Guards the case that makes an AI grader worthless: a report that covers
    most of a criterion well gets full marks, and the one thing it skipped
    stops being taught.
    """
    c = crit(n=6)
    assert rate(c, 6, 6) == "Complete"
    assert rate(c, 5, 6) == "Acceptable"


def test_below_a_third_is_missing_not_acceptable():
    """A criterion with almost nothing behind it scores zero, not full minus one.

    The course rule is that a criterion claimed with no data is Missing. Without
    this floor a student who writes one sentence per task collects 14 of 15 on
    every criterion.
    """
    c = crit(n=9)
    assert rate(c, 3, 9) == "Acceptable"
    assert rate(c, 2, 9) == "Missing"


def test_acceptable_is_full_minus_one():
    assert crit(points=15).acceptable_points == 14
    assert crit(points=20).acceptable_points == 19
    assert Criterion(name="X", points=1).acceptable_points == 0


# --- the verbatim check ------------------------------------------------------

REPORT = """\
## Task 3

```
vyos@VyOS-1:~$ show interfaces
eth0    2610:a8:483f:c00:e6d:3cff:fe26:0/64    u/u   WAN
        2610:a8:4831:38e::9d/128
```

The address 2610:a8:4831:38e::9d/128 is the DHCPv6 address, assigned by a
server rather than derived, which is why it carries a /128.
"""


def test_a_real_quote_verifies():
    assert verify_quote("2610:a8:4831:38e::9d/128 is the DHCPv6 address", REPORT)


def test_whitespace_differences_are_forgiven():
    """Word and Markdown both reflow, so a quote will not match byte for byte."""
    assert verify_quote("is the DHCPv6   address,\n  assigned by a server", REPORT)


def test_curly_punctuation_is_forgiven():
    """Word rewrites straight quotes and dashes on the way in.

    Without the fuzzy step a correct quote from a real .docx fails the check and
    a good rating gets voided, which trains the reader to ignore the flag.
    """
    assert verify_quote(
        "which is why it carries a /128…"[:-1] + ".", REPORT
    )


def test_a_fabricated_quote_does_not_verify():
    """The failure that would make a grade indefensible.

    A model asserting evidence that is not in the report has to be caught here,
    because nothing downstream can tell the difference.
    """
    assert not verify_quote(
        "The student configured NAT64 with the well known prefix on eth2", REPORT
    )


def test_a_paraphrase_does_not_verify():
    """Close is not verbatim. At the 0.92 threshold a reworded sentence fails."""
    assert not verify_quote(
        "The DHCPv6 address was given out by a server instead of being derived, "
        "so it has a /128 prefix length", REPORT
    )


def test_a_trivially_short_quote_does_not_verify():
    """Short strings match by accident and prove nothing."""
    assert not verify_quote("eth0", REPORT)


# --- findings to verdict -----------------------------------------------------

def test_fabricated_evidence_voids_the_item_and_flags_the_criterion():
    c = crit(n=3)
    response = Response(findings=[
        Finding(item=1, satisfied=True,
                quote="is the DHCPv6 address, assigned by a server"),
        Finding(item=2, satisfied=True,
                quote="The student clearly demonstrated mastery of SLAAC"),
        Finding(item=3, satisfied=False, quote=""),
    ], comment="Some of it is here.")

    v = build_verdict(c, response, REPORT)
    assert len(v.evidence) == 1
    assert v.confidence == "low"
    assert any("not found in report" in reason for reason in v.voided)
    # Item 2 was claimed satisfied but did not verify, so it does not count
    # towards the rating: one of three verified, which is Acceptable by the
    # rule. The rating is still produced, because a flagged rating tells the
    # reader more than a refusal does, and the low confidence plus the voided
    # list are what stop it being used as it stands.
    assert v.rating == "Acceptable"
    assert "bullet 2" in v.missing


def test_satisfied_without_a_quote_does_not_count():
    """A claim with nothing behind it is not evidence, by the course rule."""
    c = crit(n=3)
    response = Response(findings=[
        Finding(item=i, satisfied=True, quote="") for i in (1, 2, 3)
    ])
    v = build_verdict(c, response, REPORT)
    assert v.rating == "Missing"
    assert v.awarded == 0
    assert len(v.voided) == 3


def test_a_missing_finding_is_treated_as_unsatisfied():
    """The model returning eight findings for nine bullets must not silently
    award the ninth."""
    c = crit(n=3)
    response = Response(findings=[
        Finding(item=1, satisfied=True,
                quote="is the DHCPv6 address, assigned by a server"),
    ])
    v = build_verdict(c, response, REPORT)
    assert len(v.missing) == 2


def test_exemplary_requires_complete():
    """A model cannot mark partial work as teaching material."""
    c = crit(n=2)
    response = Response(findings=[
        Finding(item=1, satisfied=True,
                quote="is the DHCPv6 address, assigned by a server"),
        Finding(item=2, satisfied=False, quote=""),
    ], exemplary=True)
    assert build_verdict(c, response, REPORT).exemplary is False


# --- the card and its review gate --------------------------------------------

def test_the_shipped_d01_card_is_well_formed():
    c = card_mod.load(CARDS / "3100-d01.md")
    lab = __import__("clerk.lab", fromlist=["load"]).load(LABS / "3100-d01.md")
    findings = card_mod.lint(c, lab)
    # Unsigned is expected and is the only finding allowed on the draft.
    assert all("unsigned" in f for f in findings), findings
    assert c.total_points == 90
    assert len(c.criteria) == 8


def test_an_unsigned_card_is_refused():
    c = card_mod.load(CARDS / "3100-d01.md")
    with pytest.raises(card_mod.CardError):
        card_mod.require_reviewed(c)


def test_a_stale_signature_is_refused(tmp_path):
    """Editing a card has to invalidate the human review.

    This is the whole gate. If a signature survived an edit, a bullet could be
    changed after review and reach a student grade unread.
    """
    src = (CARDS / "3100-d01.md").read_text(encoding="utf-8")
    src = src.replace("reviewed_by:", "reviewed_by: saundeb1")
    old = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    src = src.replace("reviewed:\n", f"reviewed: {old}\n")
    path = tmp_path / "card.md"
    path.write_text(src, encoding="utf-8")

    c = card_mod.load(path)
    ok, why = card_mod.signature_is_current(c)
    assert not ok
    assert "stale" in why


def test_a_current_signature_passes(tmp_path):
    src = (CARDS / "3100-d01.md").read_text(encoding="utf-8")
    src = src.replace("reviewed_by:", "reviewed_by: saundeb1")
    src = src.replace("reviewed:\n", f"reviewed: {dt.date.today().isoformat()}\n")
    path = tmp_path / "card.md"
    path.write_text(src, encoding="utf-8")
    card_mod.require_reviewed(card_mod.load(path))


def test_lint_catches_a_points_mismatch(tmp_path):
    src = (CARDS / "3100-d01.md").read_text(encoding="utf-8")
    path = tmp_path / "card.md"
    path.write_text(src.replace("points: 90", "points: 75"), encoding="utf-8")
    findings = card_mod.lint(card_mod.load(path))
    assert any("points mismatch" in f for f in findings)


def test_lint_catches_an_unobservable_bullet(tmp_path):
    """A bullet about a mental state cannot be graded from a report."""
    src = (CARDS / "3100-d01.md").read_text(encoding="utf-8")
    src = src.replace("- A network diagram is present and matches the physical topology in the handout",
                      "- The student understands IPv6 addressing")
    path = tmp_path / "card.md"
    path.write_text(src, encoding="utf-8")
    findings = card_mod.lint(card_mod.load(path))
    assert any("not observable" in f for f in findings)


# --- canaries ----------------------------------------------------------------

def test_canary_survives_word_mangling_the_text():
    """Word curls quotes and swaps spaces, so a raw comparison misses the marker
    and a flagged submission gets graded anyway."""
    marker = "InventoryID=GFD7356"
    report = "...end of report. InventoryID–GFD7356".replace("–", "=")
    assert canaries.found(marker, report)


def test_canary_matching_ignores_case_and_spacing():
    assert canaries.found("InventoryID=GFD7356",
                          "inventoryid=gfd7356   at the end")


def test_no_canary_configured_never_quarantines():
    assert canaries.found(None, "anything at all") is False
    assert canaries.found("", "anything at all") is False


def test_screen_returns_only_the_hits():
    hits = canaries.screen("MARKER-123", {
        "alice": "a clean report",
        "bob": "a report ending with MARKER-123",
    })
    assert [h.student for h in hits] == ["bob"]


# --- the handout is the standard ---------------------------------------------

def test_every_criterion_carries_the_handout_objective():
    """Directive from Brandon, 2026-09-26: grade to the IMPORTANT prompts in the
    student facing lab, because that is what students were told to achieve."""
    import clerk.lab as lab_mod
    c = card_mod.load(CARDS / "3100-d01.md")
    lab = lab_mod.load(LABS / "3100-d01.md")
    for crit in c.criteria:
        assert crit.objective, f"{crit.name} has no objective"
        stated = [lab.task(n).objective for n in crit.tasks if lab.task(n)]
        assert any(card_mod._similar(crit.objective, s) for s in stated if s), \
            f"{crit.name} objective is not the handout's"


def test_a_criterion_grading_something_the_handout_never_asked_is_flagged(tmp_path):
    """The Additional Question 3 defect, generalised.

    A criterion whose objective appears nowhere in the handout is grading
    students on an instruction they never received. Lint has to catch that,
    because reading the two files side by side is exactly what nobody does.
    """
    import clerk.lab as lab_mod
    src = (CARDS / "3100-d01.md").read_text(encoding="utf-8")
    src = src.replace(
        "objective: Demonstrate the interactions between DNS and IPv6 protocols.",
        "objective: Configure BGP peering with the upstream provider.")
    path = tmp_path / "card.md"
    path.write_text(src, encoding="utf-8")
    lab = lab_mod.load(LABS / "3100-d01.md")
    findings = card_mod.lint(card_mod.load(path), lab)
    assert any("does not match the Objective line" in f for f in findings), findings


def test_the_card_matches_the_live_canvas_rubric():
    """Canvas is the authority. If the two drift, grades stop mapping to rows.

    Guards the failure this project started with: a grader card and a grading
    guide describing two different instruments for the same deliverable.
    """
    import json
    rubric = (Path(__file__).parent.parent.parent / "course-admin" / "profiles"
              / "rubrics" / "3100-d01-report.json")
    live = json.loads(rubric.read_text(encoding="utf-8"))
    c = card_mod.load(CARDS / "3100-d01.md")

    assert [(x["description"], x["points"]) for x in live["criteria"]] == \
           [(x.name, x.points) for x in c.criteria]
    assert sum(x["points"] for x in live["criteria"]) == c.total_points == 90


# --- both submission formats -------------------------------------------------

def test_pdf_font_names_are_recognised_as_monospace():
    """PDF font names arrive subset tagged, so a plain lookup misses them all.

    'ABCDEE+Consolas' is what a Word exported PDF actually carries. Without the
    tag stripping, every monospace line in every PDF reads as prose, and the
    fixed width formatting requirement becomes ungradeable.
    """
    from clerk.pdf import _is_mono_font
    for name in ("ABCDEE+Consolas", "Courier", "Courier-Bold", "BAAAAA+CourierNew",
                 "DejaVuSansMono", "Consolas-Bold"):
        assert _is_mono_font(name), name
    for name in ("ABCDEE+Calibri", "Helvetica", "TimesNewRomanPSMT", "Arial-Bold"):
        assert not _is_mono_font(name), name


def test_unknown_submission_formats_are_refused_clearly():
    """A .doc or a .odt has to fail with a message, not a stack trace."""
    from clerk.extract import extract
    with pytest.raises(ValueError, match="must be .docx or .pdf"):
        extract(Path("nope.odt"), Path("."), "student")


# --- quote decoration, from the first real run against ai-01 -----------------

def test_a_quote_wrapped_in_quotation_marks_still_verifies():
    """Eight of eleven verbatim failures on the first real run were this.

    The model returns '"set interfaces ..."' with quotation marks it added
    itself, the characters are not in the report, and a correct finding gets
    voided as fabricated. A false fabrication flag is worse than no flag,
    because it teaches the reader to ignore the real ones.
    """
    assert verify_quote('"is the DHCPv6 address, assigned by a server"', REPORT)
    assert verify_quote("'is the DHCPv6 address, assigned by a server'", REPORT)
    assert verify_quote('“is the DHCPv6 address, assigned by a server”', REPORT)


def test_a_quote_wrapped_in_a_code_fence_still_verifies():
    assert verify_quote("```\nvyos@VyOS-1:~$ show interfaces\n```", REPORT)


def test_a_quote_carrying_blockquote_markers_still_verifies():
    assert verify_quote("> is the DHCPv6 address, assigned by a server", REPORT)


def test_unwrapping_does_not_rescue_a_fabrication():
    """Stripping decoration must not become a licence to paraphrase."""
    assert not verify_quote('"The student configured NAT64 on eth2 correctly"', REPORT)


def test_too_short_is_not_reported_as_fabrication():
    """'[IMAGE-01]' is ten characters and was being called fabricated.

    Not evidence, but a different and far milder finding than the model
    inventing a quote, and it must not flag the criterion for review.
    """
    from clerk.judge import check_quote, TOO_SHORT, NOT_FOUND
    assert check_quote("[IMAGE-01]", REPORT) == TOO_SHORT
    assert check_quote("A wholly invented sentence about BGP peering", REPORT) == NOT_FOUND

    c = crit(n=2)
    response = Response(findings=[
        Finding(item=1, satisfied=True, quote="[IMAGE-01]"),
        Finding(item=2, satisfied=True,
                quote='"is the DHCPv6 address, assigned by a server"'),
    ])
    v = build_verdict(c, response, REPORT)
    assert v.voided == []              # nothing was fabricated
    assert v.confidence == "high"
    assert len(v.evidence) == 1        # the short one still does not count


def test_a_quote_stitched_from_two_places_verifies():
    """The dominant recall failure on the first real ai-01 run.

    Asked whether two things are distinguished from each other, the model
    returns the sentence about one and the sentence about the other, because
    that is where the student put them. Both are verbatim; the concatenation is
    not contiguous. Rejecting that cost correct findings on a third of the
    Task 3 bullets.
    """
    stitched = ("is the DHCPv6 address, assigned by a server rather than derived. "
                "eth0    2610:a8:483f:c00:e6d:3cff:fe26:0/64    u/u   WAN")
    assert verify_quote(stitched, REPORT)


def test_a_stitched_quote_with_one_invented_fragment_fails():
    """Fragment-wise checking must not become a hole in the fabrication guard."""
    poisoned = ("is the DHCPv6 address, assigned by a server rather than derived. "
                "The student also configured OSPFv3 across the backbone.")
    assert not verify_quote(poisoned, REPORT)


# --- reproducibility ---------------------------------------------------------

def test_grading_is_single_slot_by_default():
    """Measured on ai-01: two slots scored the same report 85, 74, 84.

    One slot scored it 81, 83, 83 with passes two and three identical on every
    criterion. Batched floating point reductions are not associative, so a
    prompt batched with different partners produces different logits, and no
    client side setting makes that reproducible.

    A grader that disagrees with itself by eleven points has no standing, so the
    default spends the parallelism to buy the determinism back.
    """
    import os
    from clerk.engine import Engine, HOSTS
    os.environ.setdefault("OHIO_API_KEY", "sk-test-only")
    assert Engine("ai01").slots == 1
    assert Engine("ai01", slots=4).slots == 4      # opt out stays available
    assert HOSTS["ai01"].slots == 2                # the host's real capacity


# --- machine checks ----------------------------------------------------------

def test_word_document_is_checked_not_judged():
    """28 of 29 students lost a point on "One Word document" while submitting
    .docx, because nothing inside a document says what container it is in. The
    model even asserted "The submission is not a Word document"."""
    from clerk.checks import Facts, run
    assert run("single_docx", Facts(student="x", source="a.docx")).satisfied
    assert not run("single_docx", Facts(student="x", source="a.pdf")).satisfied
    assert not run("single_docx", Facts(student="x", source="a.docx",
                                        file_count=2)).satisfied


def test_zero_monospace_hard_fails_the_criterion():
    """Brandon, 2026-09-27: a full points deduction, not one bullet of four.

    A report with no fixed width text anywhere did not paste command output as
    text at all. Costing one point of ten made that indistinguishable from a
    missing figure label.
    """
    from clerk.checks import Facts, run
    from clerk.card import Criterion

    zero = run("monospace_present", Facts(student="x", monospace_ratio=0.0))
    assert not zero.satisfied and zero.hard_fail
    some = run("monospace_present", Facts(student="x", monospace_ratio=0.48))
    assert some.satisfied and not some.hard_fail

    c = Criterion(name="Report Standards", points=10,
                  evidence=["One Word document", "Figures labeled",
                            "Terminal text as text", "Narrative connects"],
                  critique=["x"], checks={1: "single_docx", 3: "monospace_present"})
    r = Response(findings=[Finding(item=2, satisfied=True,
                                   quote="is the DHCPv6 address, assigned by a server"),
                           Finding(item=4, satisfied=True,
                                   quote="is the DHCPv6 address, assigned by a server")])
    facts = Facts(student="x", source="a.docx", monospace_ratio=0.0)
    v = build_verdict(c, r, REPORT, facts)
    assert v.rating == "Missing" and v.awarded == 0, (v.rating, v.awarded)


def test_checked_bullets_never_reach_the_model():
    """Asking about a fact the model cannot see produces a confident wrong
    answer, so the bullet is left out of the checklist entirely."""
    import clerk.lab as lab_mod
    from clerk.judge import build_prompt
    c = card_mod.load(CARDS / "3100-d02.md")
    lab = lab_mod.load(LABS / "3100-d02.md")
    crit = c.criterion("Report Standards")
    assert crit.checks, "the D02 card should declare machine checks"
    prompt = build_prompt(c, lab, crit, "some report text")
    assert "One Word document" not in prompt
    assert "Figures labeled" in prompt
