"""Turn embedded images into text the judge can quote from.

Two transcribers run over every image and both results are kept.

OCR (tesseract) handles the majority case, which is a screenshot of a terminal
or a Wireshark pane. That is a dense monospace text problem, not a scene
understanding problem, and OCR is better at it than a vision language model as
well as being deterministic and free. Determinism matters when the output feeds
a grade.

A vision model (gemma4 on ai-01) handles what OCR cannot: drawn network
diagrams, GNS3 canvases, anything where the topology and the labels matter more
than the characters.

Keeping both, rather than routing by image type, is deliberate for the first
few deliverables. The classifier in extract.py is cheap and will be wrong
sometimes, and reading both transcriptions side by side in vision/<student>.json
is how you find out which one is actually carrying the weight. Drop the loser
once you know.
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
from pathlib import Path

from pydantic import BaseModel, Field

from .engine import Engine, EngineError

SYSTEM = """\
You transcribe images from student network lab reports so a grader can read \
them as text. You are a transcriber, not a judge. You never say whether the \
content is correct, complete, or good.

For a screenshot of a terminal, a console, or a packet analyser: reproduce the \
text exactly, preserving line structure, including the command line and the \
prompt. Reproduce addresses, interface names and numbers character for \
character. If a character is genuinely unreadable write [?] rather than \
guessing, because a guessed hex digit in an IPv6 address becomes a wrong grade.

For a drawn diagram: list every labelled object, every interface name, every \
address, and every link between objects. Say what connects to what.

For a browser window: say which page is shown, the URL if visible, and what the page renders. This is legitimate evidence, because the point is what the browser displayed.

For anything else: describe what it shows, briefly and factually, without transcribing blocks of text.

Return only a JSON object matching the schema.\
"""

PROMPT = """\
This image appears in a student lab report for {course} Deliverable {deliverable}.

Text immediately before it in the report:
{before}

Text immediately after it:
{after}

A cheap classifier guessed this image is: {kind}. It is often wrong, so trust \
what you see.

Transcribe the image.\
"""


class Transcription(BaseModel):
    kind: str = Field(description="terminal, diagram, gns3, wireshark, ide, or other")
    transcription: str = Field(description="the text or the description")
    #: Two report standards that need to know what the image is, which pixel
    #: statistics cannot tell. See the note at the end of extract.py.
    canvas_screenshot: bool = Field(
        default=False,
        description="true only for a DIAGRAM that is a screenshot of the Draw.io "
                    "editor rather than an exported image. The tell is the "
                    "editor's background grid, plus toolbars or a shape palette. "
                    "False for any image that is not a diagram.")
    dark_background: bool = Field(
        default=False,
        description="true only for a DIAGRAM drawn light on dark. False for a "
                    "terminal, an IDE window or a packet analyser, which are "
                    "legitimately dark.")


#: Where the tesseract binary turns up. The UB-Mannheim installer defaults to a
#: per user location that is not on PATH, so relying on PATH alone silently
#: disables OCR: the module imports, every call returns empty, and nothing says
#: why. That is how this ran for a whole afternoon transcribing text screenshots
#: with a vision model.
_TESSERACT_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR	esseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR	esseract.exe",
    str(Path.home() / "AppData/Local/Programs/Tesseract-OCR/tesseract.exe"),
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
)


def tesseract_ready() -> bool:
    """Locate and configure tesseract. Cached after the first call."""
    global _TESSERACT_OK
    if _TESSERACT_OK is not None:
        return _TESSERACT_OK
    _TESSERACT_OK = False
    try:
        import shutil
        import pytesseract
    except ImportError:
        return False
    found = shutil.which("tesseract")
    if not found:
        for candidate in _TESSERACT_CANDIDATES:
            if Path(candidate).is_file():
                found = candidate
                break
    if not found:
        return False
    pytesseract.pytesseract.tesseract_cmd = found
    try:
        pytesseract.get_tesseract_version()
        _TESSERACT_OK = True
    except Exception:
        _TESSERACT_OK = False
    return _TESSERACT_OK


_TESSERACT_OK = None


def ocr(path: Path) -> str:
    """Tesseract pass. Returns an empty string if tesseract is not installed.

    Optional on purpose. The tool has to run on a machine without tesseract,
    because the vision model half still works and an install is not a blocker
    for a first pass.
    """
    if not tesseract_ready():
        return ""
    import pytesseract
    from PIL import Image as PILImage
    try:
        with PILImage.open(path) as im:
            # psm 6 assumes a uniform block of text, which is what a terminal
            # screenshot is. The default page segmentation treats it as a
            # magazine layout and shuffles the lines.
            return pytesseract.image_to_string(im, config="--psm 6").strip()
    except Exception as e:
        return f"(ocr failed: {e})"


#: Longest side sent to the vision model. Larger images are scaled down.
#:
#: Prefill, not generation, is what makes this stage slow: measured on ai-01,
#: 204 seconds per image against a median output of only 108 tokens. Cost scales
#: with pixel count, and Gemma splits a large image into several crops that are
#: each encoded in full, so an oversized screenshot is paid for several times.
#:
#: 1280, sized so a diagram's labels survive. Brandon, 2026-09-27: the meat
#: takes care of the exceptions, and an hour of GPU to read one image is not a
#: trade worth making. A transcription that is merely adequate, plus a human who
#: opens the two reports that matter, beats a perfect transcription of all 91.
#:
#: Measured on ITS 3100 D02: median image 0.41 MP, largest 3.52 MP. This touches
#: 44 of 91 images and removes about 43 percent of the total pixels.
MAX_IMAGE_EDGE = 1280


#: An OCR pass this large means the image is a picture of text.
#:
#: Measured on ITS 3100 D02, OCR character and line counts:
#:     network diagrams      163/6   346/16   429/18
#:     dense screenshots    1895/35 1922/37  2221/25  2376/41
#:
#: Text density per megapixel does NOT separate them, because a diagram's labels
#: are small and sparse over a large canvas: Daniel Isiko's diagram lands at
#: 1013 chars per MP, squarely among the terminals. Absolute size does separate
#: them, so that is what this uses.
TEXT_DUMP_CHARS = 1000
TEXT_DUMP_LINES = 22


def looks_like_text_dump(path: Path) -> tuple[bool, str]:
    """Is this image a picture of text rather than something visual?

    Cheap, deterministic, and runs before any model call. Command output pasted
    as an image is a formatting violation, not evidence, so these are never sent
    to the vision model: transcribing one would let the judge quote it and
    credit a bullet the report was not entitled to satisfy that way.

    Returns (is_text_dump, the OCR text), because the OCR is worth keeping for
    the sparse images too. It reads labels a vision model misses: on Isiko's
    diagram the model never produced "br-PublicNet" and OCR did.
    """
    text = ocr(path)
    if not text:
        return False, ""
    lines = [l for l in text.splitlines() if l.strip()]
    dense = len(text) >= TEXT_DUMP_CHARS or len(lines) >= TEXT_DUMP_LINES
    return dense, text


def _data_url(path: Path, max_edge: int = MAX_IMAGE_EDGE) -> str:
    """Base64 data URL, downscaled if oversized. Never upscaled."""
    if max_edge:
        try:
            from PIL import Image as PILImage
            with PILImage.open(path) as im:
                if max(im.size) > max_edge:
                    im = im.convert("RGB")
                    im.thumbnail((max_edge, max_edge), PILImage.LANCZOS)
                    import io
                    buf = io.BytesIO()
                    # PNG, not JPEG: these are screenshots of text, and JPEG
                    # ringing around small glyphs is exactly the artifact that
                    # turns a transcribed address into a wrong one.
                    # A screenshot is flat colour and compresses well as PNG,
                    # but LANCZOS interpolation invents intermediate shades and
                    # the result can encode LARGER than the original. Quantising
                    # back to a small palette undoes that. Bytes do not drive
                    # prefill cost, pixels do, but there is no reason to upload
                    # four times the data for a smaller image.
                    if im.getcolors(maxcolors=4096):
                        im = im.quantize(colors=256, method=PILImage.MEDIANCUT)
                    im.save(buf, "PNG", optimize=True)
                    return ("data:image/png;base64,"
                            + base64.b64encode(buf.getvalue()).decode())
        except Exception:
            pass  # unreadable or Pillow missing: send it as it is
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


#: Images transcribed per report. Beyond this they are recorded and skipped.
#:
#: Four is not an arbitrary budget, it is roughly what a correct report needs: a
#: network diagram, and a small number of genuinely visual artifacts such as a
#: browser window showing the served page. Everything else the lab asks for is
#: text and must be given as text.
#:
#: Measured on ITS 3100 D02: 24 of 29 reports were already at four or fewer, and
#: of the images sitting beyond the fourth, 18 were terminal screenshots, 11
#: unclassified and 1 Wireshark. Almost none of it was evidence the report was
#: entitled to present that way, so the cap costs little and the overflow is
#: itself a finding.
DEFAULT_MAX_IMAGES = 4


def cmd_vision(args) -> int:
    from .__main__ import Run

    run = Run(args.run)
    from . import card as card_mod
    c = run.load_card(require_signed=False)
    ext_dir, out_dir = run.path / "extract", run.dir("vision")

    try:
        engine = Engine(args.host)
    except EngineError as e:
        raise SystemExit(str(e))

    print(f"transcribing on {engine.host.name} / {engine.model}, "
          f"{engine.host.slots} slots"
          + ("" if args.no_ocr else ", plus tesseract"))

    async def run_all() -> None:
        for student in run.students():
            meta_file = ext_dir / f"{student}.meta.json"
            if not meta_file.is_file():
                continue
            dest = out_dir / f"{student}.json"
            if dest.exists() and not args.force:
                print(f"skip {student} (already transcribed, use --force)")
                continue
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            images = meta.get("images", [])
            if not images:
                dest.write_text("[]", encoding="utf-8")
                continue

            limit = args.max_images
            skipped = images[limit:] if limit else []
            images = images[:limit] if limit else images
            if skipped:
                kinds = ", ".join(sorted({i.get("kind", "unknown") for i in skipped}))
                print(f"  {student}: {len(skipped)} image(s) beyond the first "
                      f"{limit} not transcribed ({kinds})")

            entries = await asyncio.gather(*[
                _transcribe(engine, c, ext_dir / student / img["file"], img,
                            skip_ocr=args.no_ocr)
                for img in images
            ])
            # Skipped images are recorded, not silently dropped. The judge is
            # told they exist and that their contents are unavailable, so it
            # cannot credit them and cannot assume they were absent either.
            for img in skipped:
                entries.append({
                    "index": img["index"],
                    "file": img["file"],
                    "kind": img.get("kind", "unknown"),
                    "ocr": "",
                    "model": "",
                    "skipped": True,
                    "transcription": (
                        f"This image was not read. The report carries "
                        f"{len(skipped) + limit} images and only the first {limit} "
                        f"are transcribed, because a report that needs more than "
                        f"that is presenting as pictures what it was asked to "
                        f"present as text. Do not credit or discredit anything it "
                        f"might contain."),
                })
            entries.sort(key=lambda e: e["index"])
            dest.write_text(json.dumps(entries, indent=2), encoding="utf-8")
            note = f", {len(skipped)} skipped" if skipped else ""
            print(f"{student}: {len(entries) - len(skipped)} image(s){note}")

    async def main() -> None:
        # Close inside the same loop. Doing it in a second asyncio.run() runs
        # the client's teardown against a loop that is already closed, which on
        # Windows raises "Event loop is closed" and makes the process exit non
        # zero. That looks cosmetic, and is not: it broke a chained pipeline
        # after the vision stage had already succeeded, and the next three
        # stages silently never ran.
        try:
            await run_all()
        finally:
            await engine.close()

    asyncio.run(main())
    return 0


async def _transcribe(engine: Engine, card, path: Path, img: dict,
                      *, skip_ocr: bool) -> dict:
    """OCR first, then the vision model only if the image is actually visual."""
    kind = img.get("kind", "unknown")
    is_text_dump, text = (False, "") if skip_ocr else looks_like_text_dump(path)
    if kind == "wireshark":
        is_text_dump = True

    if is_text_dump:
        # Never sent to the model, and its contents are withheld from the
        # dossier so the judge cannot quote them. A picture of command output
        # is a formatting violation, not evidence, and transcribing it would
        # launder the violation into a satisfied bullet.
        return {
            "index": img["index"],
            "file": img["file"],
            "kind": "text_screenshot",
            "ocr": "",
            "model": "",
            "withheld": True,
            "transcription": (
                "A screenshot of command output or a packet analyser appears "
                "here. The report was required to give this as text, so the "
                "image is a formatting violation and not evidence. Its "
                "contents are deliberately withheld. Treat any data it claims "
                "to show as absent."
            ),
        }

    model_text = ""
    result = None
    try:
        result = await engine.ask(
            SYSTEM,
            PROMPT.format(
                course=card.meta.get("course", ""),
                deliverable=card.meta.get("deliverable", ""),
                before=img.get("context_before", "") or "(nothing)",
                after=img.get("context_after", "") or "(nothing)",
                kind=kind,
            ),
            Transcription,
            images=[_data_url(path)],
        )
        model_text = result.transcription.strip()
        kind = result.kind or kind
    except Exception as e:
        model_text = f"(vision model failed: {e})"

    # Both readings are kept. OCR catches labels the model glosses over: on one
    # network diagram the model never produced "br-PublicNet" and OCR did.
    merged = []
    if text:
        merged.append("OCR:\n" + text)
    if model_text:
        merged.append(engine.model + ":\n" + model_text)

    ok = result is not None
    return {
        "index": img["index"],
        "file": img["file"],
        "kind": kind,
        "ocr": text,
        "model": model_text,
        "withheld": False,
        "canvas_screenshot": bool(getattr(result, "canvas_screenshot", False)) if ok else False,
        "dark_background": bool(getattr(result, "dark_background", False)) if ok else False,
        "transcription": "\n\n".join(merged) or "(no transcription)",
    }


