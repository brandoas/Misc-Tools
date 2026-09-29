"""Extract a submitted .pdf into the same shape .docx produces.

ITS 3100 Deliverable 01 asks for a PDF, ITS 4750 asks for a .docx from Lab 2
onward, and the Fall 2026 D01 pile is 21 .docx against 11 .pdf, so both formats
arrive in the same assignment. Everything downstream reads one Markdown file per
student, so the split ends here.

A PDF is harder than a .docx in one way that matters. Word tells you a run's
font outright, so monospace detection is a lookup. A PDF only carries font names
per character, and a lab report sets its command output in a fixed width face,
so the font name is still the signal: it just has to be read character by
character and grouped back into lines. pdfplumber gives that; pypdf does not.

Page furniture (headers, footers, page numbers) repeats on every page and is not
evidence, so it is dropped rather than fed to the judge as content.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .extract import (MONO_FONTS, TERMINAL_RE, Extracted, Image, classify,
                      _attach_context)

#: A line is monospace if this share of its characters are set in a fixed width
#: face. Not 1.0: a pasted terminal block often picks up a proportional space or
#: a stray bullet glyph at the margins.
MONO_LINE_RATIO = 0.6

#: A short line repeating on at least this share of pages is page furniture.
FURNITURE_PAGE_RATIO = 0.6


def _is_mono_font(name: str) -> bool:
    """Is this PDF font name a fixed width face?

    PDF font names are usually subset tagged, so 'Consolas' arrives as
    'ABCDEE+Consolas' and a plain lookup misses every one of them. The tag is
    six uppercase letters and a plus, which is stripped before matching, and the
    remaining name is also checked for the word 'mono' because a lab machine
    will produce faces this list has never heard of.
    """
    n = re.sub(r"^[A-Z]{6}\+", "", name or "").strip().lower()
    n = re.sub(r"[-,](bold|italic|oblique|regular|bolditalic)$", "", n)
    if n in MONO_FONTS:
        return True
    return "mono" in n or n.startswith("courier") or n.startswith("consol")


def _line_text(chars: list[dict]) -> str:
    """Rebuild a line, inserting spaces where the PDF only left a gap.

    A PDF has no space characters inside a run that was laid out by position, so
    columns of `show interfaces` output run together without this. The gap
    threshold is relative to the glyph width, so it holds at any point size.
    """
    if not chars:
        return ""
    chars = sorted(chars, key=lambda c: c["x0"])
    out = [chars[0]["text"]]
    for prev, cur in zip(chars, chars[1:]):
        gap = cur["x0"] - prev["x1"]
        width = max(prev["x1"] - prev["x0"], 1e-6)
        if gap > width * 0.6:
            out.append(" " * max(1, int(round(gap / width))))
        out.append(cur["text"])
    return "".join(out).rstrip()


def _lines(page) -> list[tuple[str, bool]]:
    """Group a page's characters into lines of (text, is_monospace)."""
    rows: dict[int, list[dict]] = {}
    for ch in page.chars:
        # Round the baseline so characters on the same visual line group
        # together despite sub-pixel drift.
        rows.setdefault(round(ch["top"] / 2.0), []).append(ch)

    out: list[tuple[str, bool]] = []
    for key in sorted(rows):
        chars = rows[key]
        text = _line_text(chars)
        if not text.strip():
            continue
        mono = sum(1 for c in chars if _is_mono_font(c.get("fontname", "")))
        out.append((text, mono / len(chars) >= MONO_LINE_RATIO))
    return out


def _furniture(pages: list[list[tuple[str, bool]]]) -> set[str]:
    """Lines repeating across most pages: running heads, footers, page numbers.

    Kept deliberately narrow. Only short lines qualify, because a repeated long
    line is far more likely to be a student pasting the same command on every
    page, which is content.
    """
    if len(pages) < 3:
        return set()
    counts: Counter = Counter()
    for page in pages:
        for text, _ in page[:2] + page[-2:]:
            stripped = text.strip()
            if stripped and len(stripped) <= 80:
                counts[re.sub(r"\d+", "#", stripped)] += 1
    threshold = len(pages) * FURNITURE_PAGE_RATIO
    return {k for k, v in counts.items() if v >= threshold}


def extract_pdf(pdf_path: str | Path, image_dir: str | Path,
                student: str) -> Extracted:
    """Read one .pdf into Markdown plus image files on disk."""
    import pdfplumber
    from pypdf import PdfReader

    pdf_path = Path(pdf_path)
    image_dir = Path(image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(str(pdf_path)) as pdf:
        pages = [_lines(page) for page in pdf.pages]

    drop = _furniture(pages)
    images = _save_images(pdf_path, image_dir)

    out: list[str] = []
    pending: list[str] = []
    mono_chars = prose_chars = 0
    unformatted = 0
    unformatted_examples: list[str] = []
    image_cursor = 0

    def flush() -> None:
        if pending:
            out.append("```\n" + "\n".join(pending) + "\n```")
            pending.clear()

    for page_index, page in enumerate(pages):
        for text, is_mono in page:
            if re.sub(r"\d+", "#", text.strip()) in drop:
                continue
            if is_mono:
                mono_chars += len(text)
                pending.append(text)
                continue
            prose_chars += len(text)
            if TERMINAL_RE.search(text):
                unformatted += 1
                if len(unformatted_examples) < 5:
                    unformatted_examples.append(text.strip()[:110])
            flush()
            out.append(_as_heading(text))

        # A PDF gives no reliable position for an inline image relative to the
        # text, so images are anchored to the end of the page they came from.
        # That is enough for the vision stage, which only needs nearby context.
        flush()
        while image_cursor < len(images) and images[image_cursor].page == page_index:
            out.append(images[image_cursor].placeholder)
            image_cursor += 1

    flush()
    for img in images[image_cursor:]:
        out.append(img.placeholder)

    markdown = "\n\n".join(out)
    _attach_context(markdown, images)
    for img in images:
        img.kind = classify(img)

    return Extracted(student=student, markdown=markdown, images=images,
                     mono_chars=mono_chars, prose_chars=prose_chars,
                     unformatted_terminal=unformatted,
                     unformatted_examples=unformatted_examples)


def _as_heading(text: str) -> str:
    """Promote a line that reads like a task heading.

    A PDF carries no heading styles, so the only signal is the wording, and the
    judge places evidence far more reliably when the report still says 'Task 4'
    as a heading. Deliberately conservative: it matches the lab's own task and
    question numbering and nothing else.
    """
    s = text.strip()
    if re.match(r"^(Task|Step|Additional Question|Question)\s+\d+\b", s, re.I) and len(s) <= 120:
        return "## " + s
    return text


def _save_images(pdf_path: Path, image_dir: Path) -> list[Image]:
    """Pull embedded raster images out, skipping the ones that are not evidence.

    Logos, rules and spacer graphics are small, repeat, and would each cost a
    vision model call for nothing, so anything under 160 px on a side is
    dropped. A screenshot of a terminal never is.
    """
    from pypdf import PdfReader

    out: list[Image] = []
    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return out

    index = 0
    for page_number, page in enumerate(reader.pages):
        try:
            embedded = list(page.images)
        except Exception:
            continue
        for item in embedded:
            try:
                data = item.data
            except Exception:
                continue
            index += 1
            name = f"img-{index:02d}.png"
            path = image_dir / name
            try:
                path.write_bytes(data)
                from PIL import Image as PILImage
                with PILImage.open(path) as im:
                    width, height = im.size
                    if width < 160 or height < 160:
                        path.unlink(missing_ok=True)
                        index -= 1
                        continue
                    if im.format != "PNG":
                        im.convert("RGB").save(path, "PNG")
            except Exception:
                path.unlink(missing_ok=True)
                index -= 1
                continue
            img = Image(index=index, path=path, width=width, height=height)
            img.page = page_number
            out.append(img)
    return out
