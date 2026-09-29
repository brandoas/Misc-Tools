"""clerk command line.

Every stage reads files and writes files. Nothing is held between stages, so any
one of them can be run alone, rerun after a hand edit, or skipped. That is the
design constraint: this has to be a tool you could operate by hand.

    clerk doctor
    clerk card lint  <card.md>
    clerk extract    <run>
    clerk vision     <run>
    clerk assemble   <run>
    clerk judge      <run>
    clerk report     <run>
    clerk calibrate  <run>
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import json
import os
import time
import sys
from collections import Counter
from pathlib import Path


from . import canaries, card as card_mod, checks as checks_mod
from . import extract as extract_mod, lab as lab_mod
from .engine import HOSTS, Engine, EngineError
from .judge import Verdict, judge_criterion
from .report import StudentResult, cohort_report, student_sheet



class Run:
    """A run directory. Holds the inputs and every intermediate file."""

    def __init__(self, path: str | Path, *, create: bool = False):
        self.path = Path(path)
        if create:
            self.path.mkdir(parents=True, exist_ok=True)
        if not self.path.is_dir():
            sys.exit(f"no run directory at {self.path}")

    @property
    def card_path(self) -> Path:
        return self.path / "card.md"

    @property
    def lab_path(self) -> Path:
        return self.path / "lab.md"

    def dir(self, name: str) -> Path:
        d = self.path / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    #: Both formats turn up in the same assignment: ITS 3100 D01 asks for a
    #: PDF, ITS 4750 asks for a .docx from Lab 2 on, and the Fall 2026 D01 pile
    #: is 21 .docx against 11 .pdf.
    SUBMISSION_SUFFIXES = (".docx", ".docm", ".pdf")

    def submissions(self) -> dict[str, "Path"]:
        """Map student to their submission file, whatever format it arrived in.

        A student who submitted twice in two formats is reported rather than
        silently resolved, because picking one of them is a grading decision.
        """
        found: dict[str, Path] = {}
        clashes: dict[str, list[Path]] = {}
        for f in sorted((self.path / "submissions").iterdir()):
            if f.suffix.lower() not in self.SUBMISSION_SUFFIXES:
                continue
            if f.stem in found:
                clashes.setdefault(f.stem, [found[f.stem]]).append(f)
            found[f.stem] = f
        for student, paths in clashes.items():
            names = ", ".join(p.name for p in paths)
            print(f"warning: {student} has more than one submission ({names}). "
                  f"Using {found[student].name}. Remove the others.")
        return found

    def students(self) -> list[str]:
        return sorted(self.submissions())

    def load_card(self, *, require_signed: bool = True):
        c = card_mod.load(self.card_path)
        if require_signed:
            card_mod.require_reviewed(c)
        return c


def cmd_card_lint(args) -> int:
    c = card_mod.load(args.card)
    lab = None
    if args.lab:
        lab = lab_mod.load(args.lab)
    else:
        guess = Path(args.card).parent.parent / "labs" / Path(args.card).name
        if guess.is_file():
            lab = lab_mod.load(guess)

    findings = card_mod.lint(c, lab)
    print(f"{c.path.name}: {len(c.criteria)} criteria, {c.total_points} points")
    if not findings:
        print("clean")
        return 0
    for f in findings:
        print(f"  - {f}")
    print(f"\n{len(findings)} finding(s). Well formed is not the same as correct.")
    return 1


def cmd_extract(args) -> int:
    run = Run(args.run)
    c = run.load_card(require_signed=False)
    out_dir = run.dir("extract")
    meta_rows = []

    subs = run.submissions()
    for student in run.students():
        src = subs[student]
        dest = out_dir / f"{student}.md"
        if dest.exists() and not args.force:
            print(f"skip {student} (already extracted, use --force)")
            continue
        try:
            result = extract_mod.extract(src, out_dir / student, student)
        except Exception as e:
            # One unreadable submission must not stop the batch. It is reported
            # here and again in the cohort report, because a report that silently
            # never got graded is the worst outcome available.
            print(f"{student}: FAILED to read {src.name}: {e}")
            continue
        dest.write_text(result.markdown, encoding="utf-8")
        kinds = Counter(i.kind for i in result.images)
        (out_dir / f"{student}.meta.json").write_text(json.dumps({
            "student": student,
            "source": src.name,
            "images": [
                {"index": i.index, "file": i.path.name, "kind": i.kind,
                 "width": i.width, "height": i.height,
                 "context_before": i.context_before, "context_after": i.context_after}
                for i in result.images
            ],
            "monospace_ratio": round(result.monospace_ratio, 3),
            "unformatted_terminal": result.unformatted_terminal,
            "unformatted_examples": result.unformatted_examples,
        }, indent=2), encoding="utf-8")
        meta_rows.append((student, len(result.images), dict(kinds),
                          round(result.monospace_ratio, 2)))
        print(f"{student}: {src.suffix.lstrip('.')}, {len(result.markdown)} chars, "
              f"{len(result.images)} images, {result.monospace_ratio:.0%} monospace")

    if c.canary:
        texts = {s: (out_dir / f"{s}.md").read_text(encoding="utf-8")
                 for s in run.students() if (out_dir / f"{s}.md").is_file()}
        hits = canaries.screen(c.canary, texts)
        (run.path / "quarantine.json").write_text(
            json.dumps([{"student": h.student, "reason": h.reason} for h in hits],
                       indent=2), encoding="utf-8")
        if hits:
            print(f"\nquarantined {len(hits)}: {', '.join(h.student for h in hits)}")
            print("not graded, never sent to a model")
    return 0


def cmd_assemble(args) -> int:
    """Merge extracted text with image transcriptions into the judge's input.

    Kept as its own stage with no model in it, so a dossier can be hand edited
    and rejudged without re-running anything expensive.
    """
    run = Run(args.run)
    ext_dir, vis_dir, out_dir = run.path / "extract", run.path / "vision", run.dir("dossier")

    for student in run.students():
        src = ext_dir / f"{student}.md"
        if not src.is_file():
            print(f"skip {student} (not extracted)")
            continue
        text = src.read_text(encoding="utf-8")
        vis = vis_dir / f"{student}.json"
        if vis.is_file():
            for entry in json.loads(vis.read_text(encoding="utf-8")):
                if entry.get("kind") == "wireshark":
                    # A screenshot of Wireshark is not evidence, so its contents
                    # never enter the dossier.
                    #
                    # Packet data has to be presented as text. Inlining a
                    # transcription would let the judge quote it and credit the
                    # student for evidence the report was not permitted to give
                    # that way, which is worse than not reading the image at
                    # all: it launders a rule violation into a satisfied bullet.
                    # What the judge sees instead is the violation.
                    body = ("A screenshot of Wireshark appears here. Packet data "
                            "must be given as text, so this image is not evidence "
                            "and its contents are deliberately withheld. Treat any "
                            "packet data it claims to show as absent.")
                else:
                    body = entry["transcription"].strip()
                block = (f"[IMAGE-{entry['index']:02d} : {entry['kind']}]\n"
                         f"{body}\n[/IMAGE-{entry['index']:02d}]")
                text = text.replace(f"[IMAGE-{entry['index']:02d}]", block)
        (out_dir / f"{student}.md").write_text(text, encoding="utf-8")
        print(f"{student}: dossier {len(text)} chars")
    return 0


def cmd_judge(args) -> int:
    run = Run(args.run)
    c = run.load_card(require_signed=not args.unsigned)
    lab = lab_mod.load(run.lab_path)
    dossier_dir, out_dir = run.path / "dossier", run.dir("verdicts")

    quarantined = set()
    qfile = run.path / "quarantine.json"
    if qfile.is_file():
        quarantined = {q["student"] for q in json.loads(qfile.read_text(encoding="utf-8"))}

    students = [s for s in run.students() if s not in quarantined]
    if args.student:
        students = [s for s in students if s in args.student]

    try:
        engine = Engine(args.host, slots=args.slots)
    except EngineError as e:
        sys.exit(str(e))

    note = "" if engine.slots == 1 else         "  WARNING: above 1 slot, scores vary between runs on identical input"
    print(f"judging {len(students)} report(s) against {len(c.criteria)} criteria "
          f"on {engine.host.name} / {engine.model}, {engine.slots} slot(s){note}")

    async def run_all() -> None:
        await engine.warmup()
        # One student at a time, criteria concurrent within the student. The
        # report is the shared prompt prefix, so keeping a student's criteria
        # together is what lets the runner reuse its KV cache instead of
        # prefilling the whole report once per criterion.
        for student in students:
            src = dossier_dir / f"{student}.md"
            if not src.is_file():
                print(f"skip {student} (no dossier)")
                continue
            dest = out_dir / f"{student}.json"
            if dest.exists() and not args.force:
                print(f"skip {student} (already judged, use --force)")
                continue
            report = src.read_text(encoding="utf-8")
            facts = _facts_for(run, student, report)

            async def one(crit):
                """Never let a single criterion take the student down with it.

                On the first real run the thin fixture hit Open WebUI's repeat
                guard on its last criterion and the exception killed the whole
                student, discarding seven criteria that had already succeeded
                and ten minutes of GPU time. A failure here becomes a flagged
                verdict a human looks at, which is what every other unusable
                rating in this tool already does.
                """
                try:
                    return await judge_criterion(engine, c, lab, crit, report, facts)
                except Exception as exc:
                    print(f"  {student} / {crit.name}: {type(exc).__name__}: {exc}")
                    return Verdict(
                        criterion=crit.name, points=crit.points,
                        rating="Missing", awarded=0,
                        missing=list(crit.evidence),
                        comment="", confidence="low",
                        voided=[f"the model call failed: {exc}"],
                    )

            verdicts = await asyncio.gather(*[one(crit) for crit in c.criteria])
            dest.write_text(json.dumps(
                [v.to_dict() for v in verdicts], indent=2), encoding="utf-8")
            awarded = sum(v.awarded for v in verdicts)
            flags = sum(1 for v in verdicts if v.confidence == "low")
            note = f", {flags} flagged" if flags else ""
            print(f"{student}: {awarded} of {c.total_points}{note}")

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


def _facts_for(run: Run, student: str, report: str) -> checks_mod.Facts:
    """Gather what the tool knows about a submission without reading meaning."""
    meta_file = run.path / "extract" / f"{student}.meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else {}
    images = meta.get("images", [])
    return checks_mod.Facts(
        student=student,
        source=meta.get("source", ""),
        file_count=1,
        monospace_ratio=meta.get("monospace_ratio", 0.0),
        char_count=len(report),
        image_count=len(images),
        terminal_images=sum(1 for i in images if i.get("kind") == "terminal"),
        wireshark_images=sum(1 for i in images if i.get("kind") == "wireshark"),
        unformatted_terminal=meta.get("unformatted_terminal", 0),
    )


def _load_results(run: Run, c) -> tuple[list[StudentResult], list]:
    results: list[StudentResult] = []
    quarantined = []
    qfile = run.path / "quarantine.json"
    if qfile.is_file():
        quarantined = [canaries.Quarantine(**q)
                       for q in json.loads(qfile.read_text(encoding="utf-8"))]
    qnames = {q.student for q in quarantined}

    for student in run.students():
        if student in qnames:
            results.append(StudentResult(student=student, quarantined=True))
            continue
        vfile = run.path / "verdicts" / f"{student}.json"
        if not vfile.is_file():
            continue
        verdicts = [Verdict(**v) for v in json.loads(vfile.read_text(encoding="utf-8"))]
        result = StudentResult(student=student, verdicts=verdicts)
        mfile = run.path / "extract" / f"{student}.meta.json"
        if mfile.is_file():
            meta = json.loads(mfile.read_text(encoding="utf-8"))
            result.monospace_ratio = meta.get("monospace_ratio", 0.0)
            result.image_kinds = Counter(i["kind"] for i in meta.get("images", []))
        results.append(result)
    return results, quarantined


def cmd_report(args) -> int:
    run = Run(args.run)
    c = run.load_card(require_signed=False)
    results, quarantined = _load_results(run, c)
    out_dir = run.dir("review")

    for r in results:
        (out_dir / f"{r.student}.md").write_text(student_sheet(r, c), encoding="utf-8")
    cohort = cohort_report(results, c, quarantined=quarantined)
    (out_dir / "_cohort.md").write_text(cohort, encoding="utf-8")
    print(f"wrote {len(results)} sheet(s) and _cohort.md to {out_dir}")
    print()
    print(cohort)
    return 0


def cmd_calibrate(args) -> int:
    """Score the run against fixtures/expected.json.

    Only meaningful on the fixture set, where the correct rating is known by
    construction. On real submissions there is no answer key, which is the whole
    reason the fixtures exist.
    """
    run = Run(args.run)
    c = run.load_card(require_signed=False)
    expected_file = run.path / "expected.json"
    if not expected_file.is_file():
        sys.exit(f"no answer key at {expected_file}. calibrate only runs on fixtures.")
    expected = json.loads(expected_file.read_text(encoding="utf-8"))

    agree = disagree = 0
    rows: list[str] = []
    for student, wanted in sorted(expected.items()):
        vfile = run.path / "verdicts" / f"{student}.json"
        if not vfile.is_file():
            rows.append(f"{student}: not judged")
            continue
        got = {v["criterion"]: v for v in json.loads(vfile.read_text(encoding="utf-8"))}
        for criterion, want in wanted.items():
            actual = got.get(criterion)
            if actual is None:
                rows.append(f"  {student} / {criterion}: missing verdict")
                continue
            if actual["rating"] == want:
                agree += 1
            else:
                disagree += 1
                rows.append(f"  {student} / {criterion}: expected {want}, "
                            f"got {actual['rating']}")

    total = agree + disagree
    print(f"agreement: {agree} of {total} ({agree / total:.0%})" if total
          else "nothing to compare")
    if rows:
        print("\ndisagreements:")
        print("\n".join(rows))
    return 0 if disagree == 0 else 1


def _record_stage(run: "Run", stage: str, seconds: float, extra: dict | None = None) -> None:
    """Append one stage's cost to <run>/metrics.json.

    Kept per run rather than per invocation so a pipeline spread over several
    commands, or several boxes, still adds up to one account of what it took.
    """
    from .engine import metrics_summary
    path = run.path / "metrics.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"stages": []}
    entry = {"stage": stage, "seconds": round(seconds, 1),
             "finished": _dt.datetime.now().isoformat(timespec="seconds")}
    entry.update(extra or {})
    calls = metrics_summary()
    if calls:
        entry["model_calls"] = calls
    data["stages"] = [x for x in data["stages"] if x["stage"] != stage] + [entry]
    data["total_seconds"] = round(sum(x["seconds"] for x in data["stages"]), 1)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    mins = seconds / 60
    print(f"[{stage}] {mins:.1f} min")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="clerk", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    cp = sub.add_parser("card", help="work with a grader card")
    csub = cp.add_subparsers(dest="card_command", required=True)
    cl = csub.add_parser("lint", help="check a card is well formed")
    cl.add_argument("card")
    cl.add_argument("--lab", help="lab context file, to check task references")
    cl.set_defaults(func=cmd_card_lint)

    for name, fn, helptext in (
        ("extract", cmd_extract, "docx to Markdown plus images"),
        ("assemble", cmd_assemble, "merge extract and vision into a dossier"),
        ("report", cmd_report, "render review sheets and the cohort report"),
        ("calibrate", cmd_calibrate, "score against fixtures/expected.json"),
    ):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("run")
        sp.add_argument("--force", action="store_true", help="redo completed work")
        sp.set_defaults(func=fn)

    jp = sub.add_parser("judge", help="rate each report against the card")
    jp.add_argument("run")
    jp.add_argument("--host", default="ai01", choices=list(HOSTS))
    jp.add_argument("--student", action="append", help="limit to these students")
    jp.add_argument("--force", action="store_true")
    jp.add_argument("--slots", type=int, default=1,
                    help="requests in flight. 1 (default) is reproducible; "
                         "higher is faster and makes scores vary between runs")
    jp.add_argument("--unsigned", action="store_true",
                    help="run against an unsigned card. Testing only.")
    jp.set_defaults(func=cmd_judge)

    fp = sub.add_parser("fetch", help="download submissions from Canvas (read only)")
    fp.add_argument("run")
    fp.add_argument("--course", required=True, help="Canvas course id")
    fp.add_argument("--assignment", required=True, help="Canvas assignment id")
    fp.add_argument("--force", action="store_true", help="redownload existing files")
    from .canvas_io import cmd_fetch
    fp.set_defaults(func=cmd_fetch)

    np = sub.add_parser("notes", help="aggregate a graded run into lab fix notes")
    np.add_argument("run")
    np.add_argument("--out", help="where to write, default <run>/LAB-NOTES.md")
    from .notes import cmd_notes
    np.set_defaults(func=cmd_notes)

    dp = sub.add_parser("doctor", help="check the inference host is usable")
    dp.add_argument("--host", default="ai01", choices=list(HOSTS))
    from .doctor import cmd_doctor
    dp.set_defaults(func=cmd_doctor)

    vp = sub.add_parser("vision", help="transcribe embedded images")
    vp.add_argument("run")
    vp.add_argument("--host", default="ai01-vision", choices=list(HOSTS))
    vp.add_argument("--force", action="store_true")
    vp.add_argument("--no-ocr", action="store_true", help="skip the tesseract pass")
    from .vision import DEFAULT_MAX_IMAGES
    vp.add_argument("--max-images", type=int, default=DEFAULT_MAX_IMAGES,
                    help=f"images transcribed per report (default {DEFAULT_MAX_IMAGES}, "
                         f"0 for no limit). The rest are recorded as unread.")
    from .vision import cmd_vision
    vp.set_defaults(func=cmd_vision)

    args = p.parse_args(argv)
    started = time.monotonic()
    rc = args.func(args)
    stage = args.command if args.command != "card" else "card-lint"
    if getattr(args, "run", None) and stage in (
            "fetch", "extract", "vision", "assemble", "judge", "report", "notes"):
        extra = {}
        if stage in ("judge", "vision"):
            extra["host"] = getattr(args, "host", "")
        _record_stage(Run(args.run), stage, time.monotonic() - started, extra)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
