"""Turn a submitted .docx into text the judge can read.

Output is one Markdown file per student, with the document's paragraphs and
tables in order, monospace runs fenced, and every embedded image replaced by a
placeholder that the vision stage later fills in.

Two things here are evidence in their own right, not just plumbing.

Monospace detection: the lab report guidelines require CLI output, zone files
and packet data in a fixed width font, and nothing else in one. A report that
pastes command output as body text is violating the guidelines, and a report
that sets its prose in Courier is violating them the other way. Both are
gradeable, so the fencing has to reflect what the student actually did rather
than guessing from content.

Image classification: a screenshot of a terminal is a rubric violation, because
the guidelines ask for the text. A screenshot of a GNS3 canvas is not a diagram,
for the same reason. So each image is tagged, and the tag reaches the judge
alongside the transcription.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

#: Lines that are unmistakably terminal output or a shell prompt, whatever font
#: they are set in. Used to catch command output pasted as body text, which the
#: monospace ratio alone cannot see: a report can be 60 percent fixed width and
#: still have its ping output sitting in Calibri.
#:
#: This is the harm, not the aesthetics. Observed in the Fall 2026 class, an
#: `ip route` line reflowed into
#:     route4 132.235.2 itsclass@its-uc-xxx:~$
#:     itsclass@its-uc-xxx:~$ 04.192/26 metric 100
#: with the address 132.235.204.192/26 split across two lines and a prompt
#: wedged through the middle. Proportional type destroys the data.
TERMINAL_RE = re.compile(
    r"""(
      [\w.-]+@[\w.-]+[:~][^
]{0,40}[$#%]\s      # user@host:~$
    | ^\s*PS\s+[A-Za-z]:\                        # PowerShell prompt
    | ^\s*[A-Za-z]:\[^
]{0,60}>                 # cmd.exe prompt
    | ^\s*\d{1,4}\s+bytes\s+from\s               # ping reply
    | icmp_seq=\d                                  # ping reply
    | ^\s*PING\s+\S+\s*\(                        # ping header
    | ^\s*[-drwx]{10}[\s+]                         # ls -l mode bits
    | ^\s*(sudo|ssh|scp|nmcli|systemctl|hostnamectl|dig|ss|ip)\s+\S
    | SHA256:[A-Za-z0-9+/=]{20,}                    # host key fingerprint
    | ^\s*;;?\s                                     # dig comment and section lines
    | ^\s*<<>>\s*DiG                                # dig banner
    | ^\s*\S+\.\s+\d+\s+IN\s+(A|AAAA|CNAME|PTR|NS|MX)\s  # a DNS record
    | ^\s*inet6?\s                                  # ip addr output
    | ^\s*(LISTEN|ESTAB|UNCONN)\s                   # ss output
    | ^\s*\d+\s+packets\s+transmitted              # ping summary
    | rtt\s+min/avg/max                             # ping summary
    | ^\s*Non-authoritative\ answer                 # nslookup
    )""", re.M | re.X)

MONO_FONTS = {
    "courier", "courier new", "consolas", "lucida console", "monaco",
    "menlo", "dejavu sans mono", "liberation mono", "cascadia mono",
    "cascadia code", "sf mono", "roboto mono", "source code pro",
}


@dataclass
class Image:
    index: int
    path: Path
    width: int
    height: int
    kind: str = "unknown"
    context_before: str = ""
    context_after: str = ""
    #: Zero based page the image came from. Only PDFs set it; a .docx places
    #: images inline, so the placeholder position already carries the context.
    page: int = -1

    @property
    def placeholder(self) -> str:
        return f"[IMAGE-{self.index:02d}]"


@dataclass
class Extracted:
    student: str
    markdown: str
    images: list[Image] = field(default_factory=list)
    mono_chars: int = 0
    prose_chars: int = 0
    #: Terminal output found in proportional type, with a few examples.
    unformatted_terminal: int = 0
    unformatted_examples: list[str] = field(default_factory=list)

    @property
    def monospace_ratio(self) -> float:
        total = self.mono_chars + self.prose_chars
        return self.mono_chars / total if total else 0.0


def extract(path: str | Path, image_dir: str | Path, student: str) -> Extracted:
    """Read one submission into Markdown plus image files on disk.

    Dispatches on extension. ITS 3100 Deliverable 01 asks for a PDF and ITS 4750
    asks for a .docx from Lab 2 onward, and in practice both turn up in the same
    assignment, so the format split is resolved here and nothing downstream
    needs to know which one arrived.

    **Never convert one format to the other.** Each reader is native: the .docx
    path reads real font metadata out of the runs and their style chain, and the
    PDF path reads font names per character. Converting a .docx to PDF first
    would throw away the better source and inherit the harder problem, and
    round tripping through Word or LibreOffice reflows the fixed width blocks
    that the evidence quotes are checked against. The PDF fixtures in
    Grading/Cards/fixtures/make_3100_d01.py are rendered from the same content, not converted
    from the .docx files, for the same reason.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from .pdf import extract_pdf
        return extract_pdf(path, image_dir, student)
    if suffix not in (".docx", ".docm"):
        raise ValueError(
            f"{path.name}: cannot read {suffix or 'a file with no extension'}. "
            f"Submissions must be .docx or .pdf."
        )
    return extract_docx(path, image_dir, student)


#: Word's "Strict Open XML Document" save option writes ISO strict namespaces
#: (purl.oclc.org/ooxml/...) where the transitional format every tool actually
#: reads uses schemas.openxmlformats.org. python-docx rejects the strict form
#: outright. One of the 29 ITS 3100 D02 submissions was saved this way, so it is
#: a student picking the wrong entry in a Save As dropdown, not a corrupt file,
#: and it will happen again every semester.
STRICT_NS = {
    b"http://purl.oclc.org/ooxml/officeDocument/relationships":
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    b"http://purl.oclc.org/ooxml/wordprocessingml/main":
        b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    b"http://purl.oclc.org/ooxml/drawingml/main":
        b"http://schemas.openxmlformats.org/drawingml/2006/main",
    b"http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing":
        b"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    b"http://purl.oclc.org/ooxml/officeDocument/math":
        b"http://schemas.openxmlformats.org/officeDocument/2006/math",
}


def _transitional_copy(src: Path) -> Path:
    """Rewrite a strict .docx into transitional form in the scratch directory.

    The parts are identical apart from the namespace URIs, so a byte level
    substitution across the XML entries is enough. The original is never
    modified: a student submission is evidence and stays exactly as they sent
    it.
    """
    import shutil
    import tempfile
    import zipfile

    out = Path(tempfile.mkdtemp(prefix="clerk-strict-")) / src.name
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                for strict, transitional in STRICT_NS.items():
                    data = data.replace(strict, transitional)
            zout.writestr(item, data)
    return out


def extract_docx(docx_path: str | Path, image_dir: str | Path,
                 student: str) -> Extracted:
    """Read one .docx into Markdown plus image files on disk."""
    docx_path = Path(docx_path)
    image_dir = Path(image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    try:
        document = docx.Document(str(docx_path))
    except Exception as e:
        if "officeDocument" not in str(e):
            raise
        repaired = _transitional_copy(docx_path)
        document = docx.Document(str(repaired))
        print(f"  note: {docx_path.name} was saved as Strict Open XML; "
              f"read from a transitional copy")
    out: list[str] = []
    images: list[Image] = []
    mono_chars = prose_chars = 0
    flush_run = False
    unformatted = 0
    unformatted_examples: list[str] = []
    pending_mono: list[str] = []

    def flush_mono() -> None:
        if pending_mono:
            out.append("```\n" + "\n".join(pending_mono) + "\n```")
            pending_mono.clear()

    for block in _iter_blocks(document):
        if isinstance(block, Table):
            flush_mono()
            out.append(_render_table(block))
            continue

        text, is_mono, para_images = _render_paragraph(
            block, document, image_dir, len(images)
        )
        images.extend(para_images)

        if is_mono:
            mono_chars += len(text)
        else:
            prose_chars += len(text)
            if TERMINAL_RE.search(text):
                unformatted += 1
                if len(unformatted_examples) < 5:
                    unformatted_examples.append(text.strip()[:110])

        if is_mono and text.strip():
            pending_mono.append(text)
            continue

        # A blank paragraph inside a run of monospace is part of the block, not
        # the end of it. Command output is full of them, and flushing here
        # chopped one paste into several fenced blocks.
        if pending_mono and not text.strip() and not para_images:
            pending_mono.append("")
            continue

        flush_mono()
        if text.strip():
            rendered = _with_heading(block, text)
            # Flush spaced prose paragraphs form one block, as Word shows them.
            if (flush_run and not rendered.startswith("#")
                    and out and not out[-1].startswith("#")):
                out[-1] = out[-1] + "\n" + rendered
            else:
                out.append(rendered)
            flush_run = _runs_together(block)

    flush_mono()

    markdown = "\n\n".join(out)
    _attach_context(markdown, images)
    for img in images:
        img.kind = classify(img)

    return Extracted(
        student=student,
        markdown=markdown,
        images=images,
        mono_chars=mono_chars,
        prose_chars=prose_chars,
        unformatted_terminal=unformatted,
        unformatted_examples=unformatted_examples,
    )


#: A cell holding more than this is being used to lay out content, not to hold
#: a table value.
LAYOUT_CELL_CHARS = 200


def _is_layout_table(table: Table) -> bool:
    """Is this table a layout device rather than a table of values?

    Students use a one column table as a box to paste a terminal session into.
    Rendered as a Markdown table row that becomes one enormous line, the line
    structure is destroyed, the fonts are never inspected so monospace reads as
    zero, and nothing in it can be quoted.

    Measured on one ITS 3100 D02 submission: eight tables, six cells over 400
    characters, the largest holding 1,942 characters across 42 paragraphs, all
    collapsed onto single lines. It cost that student 15 points on a task they
    had actually done.

    A genuine data table, an IP grid or an address allocation, has many small
    cells. So the test is cell size, not shape.
    """
    for row in table.rows:
        for cell in row.cells:
            if len(cell.text) > LAYOUT_CELL_CHARS or len(cell.paragraphs) > 3:
                return True
    return False


def _iter_blocks(document: DocxDocument):
    """Yield paragraphs and tables in document order.

    python-docx exposes document.paragraphs and document.tables as two separate
    lists, which loses their interleaving. A lab report is mostly a sequence of
    'here is what I ran' followed by 'here is the output', so order carries
    meaning and cannot be reconstructed afterwards.
    """
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            if _is_layout_table(table):
                # Hand the cell contents to the normal paragraph path, so fonts,
                # spacing and inline images are all seen as they would be
                # anywhere else in the document.
                for row in table.rows:
                    for cell in row.cells:
                        yield from _cell_blocks(cell, document)
            else:
                yield table


def _cell_blocks(cell, document: DocxDocument):
    """Yield a cell's paragraphs and nested tables in order."""
    for child in cell._tc.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            inner = Table(child, document)
            if _is_layout_table(inner):
                for row in inner.rows:
                    for c in row.cells:
                        yield from _cell_blocks(c, document)
            else:
                yield inner


def _render_paragraph(para: Paragraph, document: DocxDocument, image_dir: Path,
                      start_index: int) -> tuple[str, bool, list[Image]]:
    """Return the paragraph text, whether it is monospace, and its images."""
    pieces: list[str] = []
    images: list[Image] = []
    mono_len = total_len = 0

    for run in para.runs:
        for blip in run._element.findall(f".//{qn('a:blip')}"):
            rid = blip.get(qn("r:embed"))
            if not rid:
                continue
            img = _save_image(document, rid, image_dir, start_index + len(images) + 1)
            if img:
                images.append(img)
                pieces.append(img.placeholder)

        if not run.text:
            continue
        pieces.append(run.text)
        total_len += len(run.text)
        if _run_is_mono(run, para):
            mono_len += len(run.text)

    text = "".join(pieces)
    is_mono = total_len > 0 and mono_len / total_len > 0.6
    return text, is_mono, images


def _run_is_mono(run, para: Paragraph) -> bool:
    """Is this run set in a fixed width font?

    Checks the run, then the paragraph style, then the style chain. Word stores
    the font on whichever level the student actually set it, and pasted terminal
    output commonly carries it on the run while a 'Code' paragraph style carries
    it on the style.
    """
    name = (run.font.name or "").strip().lower()
    if name:
        return name in MONO_FONTS
    style = run.style
    while style is not None:
        font = getattr(style, "font", None)
        sname = (getattr(font, "name", None) or "").strip().lower()
        if sname:
            return sname in MONO_FONTS
        style = getattr(style, "base_style", None)
    pstyle = para.style
    while pstyle is not None:
        font = getattr(pstyle, "font", None)
        pname = (getattr(font, "name", None) or "").strip().lower()
        if pname:
            return pname in MONO_FONTS
        if "code" in (pstyle.name or "").lower():
            return True
        pstyle = getattr(pstyle, "base_style", None)
    return False


def _space_after(para: Paragraph) -> int | None:
    """Resolve a paragraph's space-after through the style chain.

    None on the paragraph means inherit, so the value has to be looked up the
    same way Word does: direct formatting, then the paragraph style, then its
    base styles. Returns twips, or None if nothing in the chain sets it.
    """
    direct = para.paragraph_format.space_after
    if direct is not None:
        return direct.twips
    style = para.style
    while style is not None:
        fmt = getattr(style, "paragraph_format", None)
        value = getattr(fmt, "space_after", None)
        if value is not None:
            return value.twips
        style = getattr(style, "base_style", None)
    return None


def _runs_together(para: Paragraph) -> bool:
    """Does this paragraph sit flush against the next one?

    Word renders consecutive paragraphs with space-after of zero as a single
    block with no gap, which is how a student who pastes forty lines of ping
    output gets something that looks like one listing.

    Markdown has no such notion, so joining every prose paragraph with a blank
    line turned that listing into forty double spaced stanzas in the review
    sheet, and gave the judge forty separate paragraphs where the student and
    the reader both see one block. The spacing was in the document all along
    and this reads it.

    Note this says nothing about the font. A student can be flush spaced and
    still be in Times New Roman, which is exactly the case that prompted this.
    """
    return _space_after(para) == 0


def _with_heading(para: Paragraph, text: str) -> str:
    """Preserve Word heading levels as Markdown headings.

    The judge needs them: an Evidence bullet about Task 4 is far easier to place
    when the report still says 'Task 4' as a heading rather than as one more
    line of body text.
    """
    style = (para.style.name or "") if para.style else ""
    m = re.match(r"Heading (\d)", style)
    if m:
        return "#" * min(int(m.group(1)), 6) + " " + text.strip()
    if style.lower() == "title":
        return "# " + text.strip()
    return text


def _render_table(table: Table) -> str:
    rows = []
    for row in table.rows:
        cells = [c.text.replace("\n", " ").strip() for c in row.cells]
        rows.append("| " + " | ".join(cells) + " |")
    if not rows:
        return ""
    sep = "| " + " | ".join("---" for _ in table.rows[0].cells) + " |"
    return "\n".join([rows[0], sep, *rows[1:]])


def _save_image(document: DocxDocument, rid: str, image_dir: Path,
                index: int) -> Image | None:
    try:
        part = document.part.related_parts[rid]
    except KeyError:
        return None
    blob = part.blob
    ext = (part.content_type or "").rsplit("/", 1)[-1].lower()
    ext = {"jpeg": "jpg", "x-emf": "emf", "x-wmf": "wmf"}.get(ext, ext) or "png"
    path = image_dir / f"img-{index:02d}.{ext}"
    path.write_bytes(blob)

    width = height = 0
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            width, height = im.size
    except Exception:
        pass

    return Image(index=index, path=path, width=width, height=height)


def _attach_context(markdown: str, images: list[Image], window: int = 240) -> None:
    """Record the text around each placeholder.

    A Wireshark screenshot read on its own is a list of packets. Read next to
    'Task 6, step 17, capture on the LAN1 link' it is either evidence for that
    criterion or it is not, so the vision pass gets the surrounding text too.
    """
    for img in images:
        pos = markdown.find(img.placeholder)
        if pos < 0:
            continue
        img.context_before = markdown[max(0, pos - window):pos].strip()
        img.context_after = markdown[pos + len(img.placeholder):
                                     pos + len(img.placeholder) + window].strip()


def classify(img: Image) -> str:
    """Tag an image as terminal, diagram, gns3, or unknown.

    Cheap and deliberately conservative. The tag is a hint carried to the judge
    alongside the transcription, not a verdict: a wrong tag should cost nothing,
    because the transcription is what the rating actually rests on.

    Terminal screenshots are dark, low colour, and dense with small horizontal
    text. Drawn diagrams are light, low colour, and sparse. GNS3 canvases are
    light with a handful of saturated device icons.
    """
    try:
        from PIL import Image as PILImage
    except ImportError:
        return "unknown"
    try:
        with PILImage.open(img.path) as im:
            im = im.convert("RGB")
            small = im.resize((160, 160))
            pixels = list(small.getdata())
    except Exception:
        return "unknown"

    if _looks_like_wireshark(im):
        return "wireshark"

    n = len(pixels)
    brightness = sum(sum(p) / 3 for p in pixels) / n
    distinct = len({(r // 32, g // 32, b // 32) for r, g, b in pixels})
    saturation = sum(max(p) - min(p) for p in pixels) / n

    if brightness < 90 and distinct < 40:
        return "terminal"
    if brightness > 180 and distinct < 25 and saturation < 25:
        return "diagram"
    if brightness > 140 and saturation > 40:
        return "gns3"
    if brightness > 170 and distinct < 60:
        return "terminal"  # light theme terminal, common on Windows
    return "unknown"


def _looks_like_wireshark(im) -> bool:
    """Is this a screenshot of the Wireshark packet list?

    The signal is how OFTEN the row colour changes, not how colourful the image
    is. Wireshark colourises per packet, so the list is a stack of thin rows
    about twenty pixels tall and the mean row colour changes constantly. A
    Draw.io diagram is also full of pale tints but holds each one across a large
    block, and a terminal holds one colour throughout.

    Measured on this class's submissions, transitions per row of height:

        true Wireshark      0.198  0.429  0.245
        Draw.io diagram     0.103
        browser window      0.040
        terminal capture    0.107

    The first detector here tested for tinted rows instead and was wrong: the
    diagram scored 0.87 tinted against Wireshark's 0.20 to 0.33, the highest in
    the set, so it flagged 20 of 29 reports including network diagrams. Tinting
    is kept only as a weak floor to keep pure black and white text out.
    """
    w, h = im.size
    if w < 400 or h < 150 or w < h:
        return False

    px = im.load()
    step = max(1, w // 60)
    rows = []
    for y in range(h):
        r = g = b = n = 0
        for x in range(0, w, step):
            pr, pg, pb = px[x, y]
            r += pr; g += pg; b += pb; n += 1
        rows.append((r / n, g / n, b / n))

    transitions = sum(
        1 for a, c in zip(rows, rows[1:])
        if sum(abs(p - q) for p, q in zip(a, c)) > 24)
    tinted = sum(1 for (r, g, b) in rows
                 if (r + g + b) / 3 > 110 and max(r, g, b) - min(r, g, b) > 8)

    return transitions / h >= 0.15 and tinted / h >= 0.12


# NOT IMPLEMENTED HERE, and deliberately so: two diagram requirements that need
# to know what an image IS, which pixel statistics cannot tell.
#
# 1. **Draw.io export, not a screenshot.** A canvas screenshot carries the
#    editor's background grid. Autocorrelation of row and column luminance does
#    not find it: the exports scored HIGHER than the screenshots (Isiko export
#    gx 0.89, Wireshark screenshot gx 0.39), because it measures the diagram's
#    own shapes and the regular spacing of text rows. A first attempt flagged 87
#    of about 100 images.
#
# 2. **No dark mode.** Diagrams are read and printed on white, and a dark export
#    inverts to unreadable. Detecting a dark background is trivial, but useless
#    unmoderated: 37 images came back dark and the first one inspected was a VS
#    Code window in dark theme, which is *legitimate* evidence for Task 7. The
#    check needs to fire on diagrams and nothing else, and classify() cannot
#    reliably pick a diagram out. It labelled a real Draw.io network diagram
#    "unknown".
#
# Both are easy for the vision pass and hard here. A vision model looking at the
# image can say "Draw.io canvas with the grid visible" or "network diagram on a
# dark background" directly. So these belong in vision.py as things the
# transcription must report, not as heuristics over pixels. See the
# Transcription schema.


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
