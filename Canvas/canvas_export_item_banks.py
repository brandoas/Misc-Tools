#!/usr/bin/env python3
"""
canvas_export_item_banks.py

Exports Canvas question banks (item banks) for a course to three formats:
  1. item_banks.json  - Full raw data for programmatic use
  2. item_banks.md    - Markdown for uploading to Claude web (claude.ai)
  3. qti/             - QTI 1.2 XML files importable back into Canvas

Supports both Classic Quizzes (/api/v1) and New Quizzes (/api/quiz/v1) —
the correct API is detected automatically.

Usage:
    python canvas_export_item_banks.py

.env variables:
    ACCESS_TOKEN  - Canvas API access token
    CANVAS_URL    - Canvas instance base URL (e.g., https://myschool.instructure.com)
                    Falls back to stripping /api/graphql from API_URL if not set.
    COURSE_ID     - (optional) Course ID; prompts at runtime if not set
"""

import html
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

import requests
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "").strip()
CANVAS_URL = os.getenv("CANVAS_URL", "").rstrip("/")
COURSE_ID = os.getenv("COURSE_ID", "").strip()

# Derive CANVAS_URL from API_URL (GraphQL endpoint) if not set explicitly
if not CANVAS_URL:
    api_url = os.getenv("API_URL", "")
    if api_url:
        CANVAS_URL = api_url.replace("/api/graphql", "").rstrip("/")

if not ACCESS_TOKEN:
    raise ValueError("Missing ACCESS_TOKEN in .env")
if not CANVAS_URL:
    raise ValueError(
        "Missing CANVAS_URL in .env (e.g., https://myschool.instructure.com)"
    )
if not COURSE_ID:
    COURSE_ID = input("Enter Canvas course ID: ").strip()

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}


# ---------------------------------------------------------------------------
# Canvas REST API helpers
# ---------------------------------------------------------------------------

def get_all(url, params=None):
    """Fetch all pages from a paginated Canvas REST endpoint (Link-header paging)."""
    results = []
    current_params = {**(params or {}), "per_page": 100}
    while url:
        r = requests.get(url, headers=HEADERS, params=current_params)
        r.raise_for_status()
        data = r.json()
        # Some New Quizzes endpoints wrap results in {"data": [...]}
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            results.extend(data["data"])
        elif isinstance(data, list):
            results.extend(data)
        else:
            results.append(data)
        url = None
        current_params = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return results


# ---------------------------------------------------------------------------
# Classic Quizzes API  (/api/v1)
# ---------------------------------------------------------------------------

def classic_get_banks(course_id):
    return get_all(f"{CANVAS_URL}/api/v1/courses/{course_id}/question_banks")


def classic_get_questions(bank_id):
    return get_all(f"{CANVAS_URL}/api/v1/question_banks/{bank_id}/questions")


# ---------------------------------------------------------------------------
# New Quizzes API  (/api/quiz/v1)
# ---------------------------------------------------------------------------

NQ_TYPE_MAP = {
    "multiple-choice":        "multiple_choice_question",
    "true-false":             "true_false_question",
    "multi-answer":           "multiple_answers_question",
    "matching":               "matching_question",
    "ordering":               "ordering_question",
    "short-answer":           "short_answer_question",
    "fill-blank-multi":       "fill_in_multiple_blanks_question",
    "essay":                  "essay_question",
    "file-upload":            "file_upload_question",
    "numeric":                "numerical_question",
    "categorization":         "categorization_question",
    "hot-spot":               "hot_spot_question",
    "rich-fill-blank":        "fill_in_multiple_blanks_question",
}


def nq_get_banks(course_id):
    return get_all(f"{CANVAS_URL}/api/quiz/v1/courses/{course_id}/item_banks")


def nq_get_items(bank_id):
    return get_all(f"{CANVAS_URL}/api/quiz/v1/item_banks/{bank_id}/items")


def _nq_normalize_item(raw):
    """
    Convert a New Quizzes item (from /api/quiz/v1) into the Classic-style
    question dict used by the rest of this script.
    """
    # The item may be wrapped in an {"entry_type": "Item", "entry": {...}} envelope
    entry = raw.get("entry", raw)

    itype_slug = entry.get("interaction_type_slug", "")
    qtype = NQ_TYPE_MAP.get(itype_slug, itype_slug or "unknown")

    interaction = entry.get("interaction_data") or {}
    scoring = entry.get("scoring_data") or {}
    feedback = entry.get("feedback") or {}
    answer_feedback = entry.get("answer_feedback") or {}

    q = {
        "id": entry.get("id", raw.get("id", "")),
        "question_name": entry.get("title", ""),
        "question_text": entry.get("body", ""),
        "question_type": qtype,
        "points_possible": entry.get("points_possible", 1),
        "correct_comments": (feedback.get("correct") or {}).get("body", ""),
        "incorrect_comments": (feedback.get("incorrect") or {}).get("body", ""),
        "neutral_comments": (feedback.get("neutral") or {}).get("body", ""),
        "answers": [],
        "matching_answer_incorrect_matches": "",
        "_api_type": "new_quizzes",
        "_raw": raw,
    }

    # --- Build normalized answers ---
    if qtype in ("multiple_choice_question", "true_false_question"):
        correct_id = scoring.get("value", "")
        for choice in interaction.get("choices", []):
            cid = choice.get("id", "")
            q["answers"].append({
                "id": cid,
                "html": choice.get("item_body", ""),
                "text": strip_html(choice.get("item_body", "")),
                "weight": 100 if cid == correct_id else 0,
                "comments": (answer_feedback.get(cid) or {}).get("body", ""),
            })

    elif qtype == "multiple_answers_question":
        correct_ids = set(scoring.get("value", []))
        for choice in interaction.get("choices", []):
            cid = choice.get("id", "")
            q["answers"].append({
                "id": cid,
                "html": choice.get("item_body", ""),
                "text": strip_html(choice.get("item_body", "")),
                "weight": 100 if cid in correct_ids else 0,
                "comments": (answer_feedback.get(cid) or {}).get("body", ""),
            })

    elif qtype == "matching_question":
        # stems = left side, answers = right side
        stems = interaction.get("stems", [])
        right_answers = interaction.get("answers", [])
        distractors = interaction.get("distractors", [])
        # scoring.value = list of {"item_id": stem_id, "scoring_item_id": ans_id}
        correct_map = {
            m.get("item_id"): m.get("scoring_item_id")
            for m in (scoring.get("value") or [])
        }
        right_by_id = {a.get("id"): strip_html(a.get("item_body", "")) for a in right_answers}
        for stem in stems:
            sid = stem.get("id", "")
            correct_right_id = correct_map.get(sid, "")
            q["answers"].append({
                "id": sid,
                "text": strip_html(stem.get("item_body", "")),
                "html": stem.get("item_body", ""),
                "right": right_by_id.get(correct_right_id, ""),
                "weight": 100 if correct_right_id else 0,
            })
        distractor_texts = [strip_html(d.get("item_body", "")) for d in distractors]
        q["matching_answer_incorrect_matches"] = "\n".join(distractor_texts)

    elif qtype in ("short_answer_question", "fill_in_multiple_blanks_question"):
        for i, val in enumerate(scoring.get("value") or []):
            answer_text = val if isinstance(val, str) else val.get("answer", "")
            q["answers"].append({
                "id": f"ans_{i}",
                "text": answer_text,
                "html": answer_text,
                "weight": 100,
                "blank_id": val.get("blank_id", "blank") if isinstance(val, dict) else "blank",
            })

    elif qtype == "numerical_question":
        val = scoring.get("value")
        if isinstance(val, dict):
            q["answers"].append({
                "id": "ans_0",
                "numerical_answer_type": "exact_answer",
                "exact": val.get("exact", val.get("value", 0)),
                "margin": val.get("margin", 0),
                "text": str(val.get("exact", val.get("value", ""))),
                "weight": 100,
            })
        elif isinstance(val, list):
            for i, v in enumerate(val):
                q["answers"].append({
                    "id": f"ans_{i}",
                    "numerical_answer_type": v.get("type", "range_answer"),
                    "start": v.get("min", v.get("start", 0)),
                    "end": v.get("max", v.get("end", 0)),
                    "exact": v.get("exact", 0),
                    "margin": v.get("margin", 0),
                    "text": str(v.get("exact", "")),
                    "weight": 100,
                })

    elif qtype == "ordering_question":
        # scoring.value = list of ordered IDs
        correct_order = scoring.get("value", [])
        choices = {c.get("id"): strip_html(c.get("item_body", ""))
                   for c in interaction.get("choices", [])}
        for i, cid in enumerate(correct_order):
            q["answers"].append({
                "id": cid,
                "text": choices.get(cid, cid),
                "html": choices.get(cid, cid),
                "weight": 100,
                "position": i + 1,
            })

    # essay / file-upload / text-only / unknown → no answers needed

    return q


def nq_normalize_bank(raw_bank, items):
    """Wrap a New Quizzes bank + its items into the standard bank dict."""
    return {
        "id": raw_bank.get("id", ""),
        "title": raw_bank.get("title", raw_bank.get("name", "(Untitled)")),
        "questions": [_nq_normalize_item(it) for it in items],
        "_api_type": "new_quizzes",
        "_raw": raw_bank,
    }


# ---------------------------------------------------------------------------
# Markdown export (for Claude web interface)
# ---------------------------------------------------------------------------

def strip_html(text):
    """Remove HTML tags and decode entities for plain-text output."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def question_to_md(q, idx):
    lines = []
    qtype = q.get("question_type", "unknown")
    pts = q.get("points_possible", 1)
    qname = q.get("question_name", "").strip()
    qid = q["id"]

    heading = f"### Q{idx}"
    if qname and qname.lower() not in ("question", f"question {idx}"):
        heading += f": {qname}"
    heading += f"  `{qtype}`  [{pts} pt{'s' if pts != 1 else ''}]  *(ID: {qid})*"
    lines.append(heading)

    qtext = strip_html(q.get("question_text", ""))
    if qtext:
        lines.append(f"\n{qtext}\n")

    answers = q.get("answers", [])

    if qtype in ("multiple_choice_question", "true_false_question"):
        for i, ans in enumerate(answers):
            correct = ans.get("weight", 0) == 100
            text = strip_html(ans.get("html", ans.get("text", "")))
            label = chr(65 + i)
            lines.append(
                f"- **{label}. {text}** *(correct)*" if correct else f"- {label}. {text}"
            )

    elif qtype == "multiple_answers_question":
        lines.append("*(Select all that apply)*")
        for i, ans in enumerate(answers):
            correct = ans.get("weight", 0) > 0
            text = strip_html(ans.get("html", ans.get("text", "")))
            label = chr(65 + i)
            marker = "x" if correct else " "
            lines.append(f"- [{marker}] {label}. {text}")

    elif qtype == "matching_question":
        lines.append("*Match the following:*")
        for ans in answers:
            left = strip_html(ans.get("text", ""))
            right = strip_html(ans.get("right", ""))
            lines.append(f"- {left} → {right}")
        incorrect = q.get("matching_answer_incorrect_matches", "").strip()
        if incorrect:
            distractors = ", ".join(incorrect.splitlines())
            lines.append(f"\n*Distractors (right-side only):* {distractors}")

    elif qtype == "ordering_question":
        lines.append("*Correct order:*")
        sorted_ans = sorted(answers, key=lambda a: a.get("position", 0))
        for i, ans in enumerate(sorted_ans, 1):
            text = strip_html(ans.get("html", ans.get("text", "")))
            lines.append(f"  {i}. {text}")

    elif qtype == "short_answer_question":
        correct = [strip_html(a.get("text", "")) for a in answers if a.get("weight", 0) > 0]
        lines.append(f"**Correct answer(s):** {', '.join(correct) or '(none set)'}")

    elif qtype in ("fill_in_multiple_blanks_question", "multiple_dropdowns_question"):
        by_blank = defaultdict(list)
        for ans in answers:
            blank = ans.get("blank_id", "blank")
            if ans.get("weight", 0) > 0:
                by_blank[blank].append(strip_html(ans.get("text", "")))
        for blank, vals in by_blank.items():
            lines.append(f"**[{blank}]:** {', '.join(vals)}")

    elif qtype == "numerical_question":
        for ans in answers:
            atype = ans.get("numerical_answer_type", "")
            if atype == "exact_answer":
                lines.append(
                    f"**Correct:** {ans.get('exact', '')} (margin: ±{ans.get('margin', 0)})"
                )
            elif atype == "range_answer":
                lines.append(
                    f"**Correct range:** {ans.get('start', '')} to {ans.get('end', '')}"
                )
            elif atype == "precision_answer":
                lines.append(
                    f"**Correct (precision):** {ans.get('approximate', '')} "
                    f"±{ans.get('precision', '')}%"
                )
            else:
                lines.append(f"**Correct:** {ans.get('exact', ans.get('text', ''))}")

    elif qtype in ("essay_question", "file_upload_question", "text_only_question"):
        lines.append("*(No auto-graded answers)*")

    else:
        if answers:
            lines.append(f"*(Answers: {len(answers)} — see JSON export for details)*")

    # Feedback
    for key, label in [
        ("correct_comments", "Correct feedback"),
        ("incorrect_comments", "Incorrect feedback"),
        ("neutral_comments", "General feedback"),
    ]:
        text = strip_html(q.get(key, ""))
        if text:
            lines.append(f"\n> **{label}:** {text}")

    return "\n".join(lines)


def export_markdown(banks, course_id, output_path):
    lines = [
        "# Canvas Item Banks Export",
        f"**Course ID:** {course_id}",
        f"**Canvas URL:** {CANVAS_URL}",
        f"**Export Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Total Banks:** {len(banks)}",
        "",
        "---",
        "",
        "## Instructions for Claude",
        "This file contains all question banks exported from Canvas.",
        "Please help reorganize these questions, fix any issues, and output a revised",
        "version in this same Markdown format so it can be converted back to QTI for",
        "Canvas import.",
        "",
        "---",
        "",
    ]

    for bank in banks:
        api_note = " *(New Quizzes)*" if bank.get("_api_type") == "new_quizzes" else ""
        lines.append(f"## Bank: {bank['title']}{api_note}")
        lines.append(
            f"**Bank ID:** {bank['id']} | **Questions:** {len(bank['questions'])}"
        )
        lines.append("")
        for i, q in enumerate(bank["questions"], 1):
            lines.append(question_to_md(q, i))
            lines.append("")
            lines.append("---")
            lines.append("")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# QTI 1.2 export
# ---------------------------------------------------------------------------

def _pretty_xml(root):
    rough = tostring(root, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(indent="  ")


def _answer_ident(ans):
    return f"answer_{re.sub(r'[^a-zA-Z0-9_]', '_', str(ans['id']))}"


def _add_setvar(parent, value="100"):
    sv = SubElement(parent, "setvar", action="Set", varname="SCORE")
    sv.text = str(value)


def _add_feedback(item, fb_id, text):
    fb = SubElement(item, "itemfeedback", ident=fb_id, view="All")
    flow = SubElement(fb, "flow_mat")
    mat = SubElement(flow, "material")
    SubElement(mat, "mattext", texttype="text/html").text = text


def question_to_qti_item(q):
    qid = re.sub(r"[^a-zA-Z0-9_]", "_", str(q["id"]))
    qtype = q.get("question_type", "unknown")
    pts = float(q.get("points_possible", 1))
    title = html.unescape(q.get("question_name", f"Question {qid}"))

    item = Element("item", ident=f"q_{qid}", title=title)

    # Metadata
    meta_root = SubElement(item, "itemmetadata")
    qtimeta = SubElement(meta_root, "qtimetadata")
    for label, entry in [
        ("question_type", qtype),
        ("points_possible", str(pts)),
        ("assessment_question_identifierref", str(q["id"])),
    ]:
        f = SubElement(qtimeta, "qtimetadatafield")
        SubElement(f, "fieldlabel").text = label
        SubElement(f, "fieldentry").text = entry

    # Presentation
    pres = SubElement(item, "presentation")
    mat = SubElement(pres, "material")
    SubElement(mat, "mattext", texttype="text/html").text = q.get("question_text", "")

    answers = q.get("answers", [])

    # Response + resprocessing
    if qtype in ("multiple_choice_question", "true_false_question"):
        resp = SubElement(pres, "response_lid", ident="response1", rcardinality="Single")
        render = SubElement(resp, "render_choice")
        for ans in answers:
            lbl = SubElement(render, "response_label", ident=_answer_ident(ans))
            SubElement(SubElement(lbl, "material"), "mattext", texttype="text/html").text = (
                ans.get("html", ans.get("text", ""))
            )
        rp = SubElement(item, "resprocessing")
        SubElement(SubElement(rp, "outcomes"), "decvar",
                   maxvalue="100", minvalue="0", varname="SCORE", vartype="Decimal")
        for ans in answers:
            if ans.get("weight", 0) == 100:
                cond = SubElement(rp, "respcondition", **{"continue": "No"})
                SubElement(SubElement(cond, "conditionvar"), "varequal",
                           respident="response1").text = _answer_ident(ans)
                _add_setvar(cond)
                break

    elif qtype == "multiple_answers_question":
        resp = SubElement(pres, "response_lid", ident="response1", rcardinality="Multiple")
        render = SubElement(resp, "render_choice")
        for ans in answers:
            lbl = SubElement(render, "response_label", ident=_answer_ident(ans))
            SubElement(SubElement(lbl, "material"), "mattext", texttype="text/html").text = (
                ans.get("html", ans.get("text", ""))
            )
        rp = SubElement(item, "resprocessing")
        SubElement(SubElement(rp, "outcomes"), "decvar",
                   maxvalue="100", minvalue="0", varname="SCORE", vartype="Decimal")
        correct_ids = [_answer_ident(a) for a in answers if a.get("weight", 0) > 0]
        if correct_ids:
            cond = SubElement(rp, "respcondition", **{"continue": "No"})
            and_el = SubElement(SubElement(cond, "conditionvar"), "and")
            for aid in correct_ids:
                SubElement(and_el, "varequal", respident="response1").text = aid
            _add_setvar(cond)

    elif qtype in ("short_answer_question", "fill_in_multiple_blanks_question"):
        resp = SubElement(pres, "response_str", ident="response1", rcardinality="Single")
        SubElement(resp, "render_fib")
        rp = SubElement(item, "resprocessing")
        SubElement(SubElement(rp, "outcomes"), "decvar",
                   maxvalue="100", minvalue="0", varname="SCORE", vartype="Decimal")
        for ans in answers:
            if ans.get("weight", 0) > 0:
                cond = SubElement(rp, "respcondition", **{"continue": "No"})
                SubElement(SubElement(cond, "conditionvar"), "varequal",
                           respident="response1").text = ans.get("text", "")
                _add_setvar(cond)

    elif qtype == "essay_question":
        resp = SubElement(pres, "response_str", ident="response1", rcardinality="Single")
        SubElement(resp, "render_fib", rows="50", columns="100")
        rp = SubElement(item, "resprocessing")
        SubElement(SubElement(rp, "outcomes"), "decvar",
                   maxvalue="100", minvalue="0", varname="SCORE", vartype="Decimal")

    elif qtype == "numerical_question":
        resp = SubElement(pres, "response_num", ident="response1", rcardinality="Single")
        SubElement(resp, "render_fib", fibtype="Decimal")
        rp = SubElement(item, "resprocessing")
        SubElement(SubElement(rp, "outcomes"), "decvar",
                   maxvalue="100", minvalue="0", varname="SCORE", vartype="Decimal")
        for ans in answers:
            atype = ans.get("numerical_answer_type", "")
            cond = SubElement(rp, "respcondition", **{"continue": "No"})
            condvar = SubElement(cond, "conditionvar")
            try:
                if atype in ("exact_answer", ""):
                    exact = float(ans.get("exact", ans.get("text", 0)))
                    margin = float(ans.get("margin", 0))
                    and_el = SubElement(condvar, "and")
                    SubElement(and_el, "vargte", respident="response1").text = str(exact - margin)
                    SubElement(and_el, "varlte", respident="response1").text = str(exact + margin)
                elif atype == "range_answer":
                    and_el = SubElement(condvar, "and")
                    SubElement(and_el, "vargte", respident="response1").text = str(ans.get("start", 0))
                    SubElement(and_el, "varlte", respident="response1").text = str(ans.get("end", 0))
                else:
                    SubElement(condvar, "other")
            except (TypeError, ValueError):
                SubElement(condvar, "other")
            _add_setvar(cond)

    elif qtype == "matching_question":
        right_items = []
        seen = set()
        for ans in answers:
            r = ans.get("right", "").strip()
            if r and r not in seen:
                right_items.append(r)
                seen.add(r)
        for distractor in q.get("matching_answer_incorrect_matches", "").splitlines():
            d = distractor.strip()
            if d and d not in seen:
                right_items.append(d)
                seen.add(d)

        for i, ans in enumerate(answers):
            resp_id = f"response_{i + 1}"
            resp = SubElement(pres, "response_lid", ident=resp_id, rcardinality="Single")
            SubElement(SubElement(resp, "material"), "mattext", texttype="text/html").text = (
                ans.get("html", ans.get("text", ""))
            )
            render = SubElement(resp, "render_choice")
            for j, right_text in enumerate(right_items):
                lbl = SubElement(render, "response_label", ident=f"match_{j + 1}")
                SubElement(SubElement(lbl, "material"), "mattext").text = right_text

        rp = SubElement(item, "resprocessing")
        SubElement(SubElement(rp, "outcomes"), "decvar",
                   maxvalue="100", minvalue="0", varname="SCORE", vartype="Decimal")
        share = round(100 / len(answers)) if answers else 100
        for i, ans in enumerate(answers):
            correct_right = ans.get("right", "").strip()
            if correct_right in right_items:
                correct_idx = right_items.index(correct_right) + 1
                cond = SubElement(rp, "respcondition", **{"continue": "Yes"})
                SubElement(SubElement(cond, "conditionvar"), "varequal",
                           respident=f"response_{i + 1}").text = f"match_{correct_idx}"
                _add_setvar(cond, share)

    else:
        # Generic / unsupported type — export question text only
        rp = SubElement(item, "resprocessing")
        SubElement(SubElement(rp, "outcomes"), "decvar",
                   maxvalue="100", minvalue="0", varname="SCORE", vartype="Decimal")

    # Feedback
    for fb_key, fb_id in [
        ("correct_comments", "correct_fb"),
        ("incorrect_comments", "incorrect_fb"),
        ("neutral_comments", "general_fb"),
    ]:
        fb_text = (q.get(fb_key) or "").strip()
        if fb_text:
            _add_feedback(item, fb_id, fb_text)

    return item


def bank_to_qti_root(bank):
    root = Element(
        "questestinterop",
        attrib={
            "xmlns": "http://www.imsglobal.org/xsd/ims_qtiasiv1p2",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": (
                "http://www.imsglobal.org/xsd/ims_qtiasiv1p2 "
                "http://www.imsglobal.org/xsd/ims_qtiasiv1p2p1.xsd"
            ),
        },
    )
    bank_ident = re.sub(r"[^a-zA-Z0-9_]", "_", str(bank["id"]))
    ob = SubElement(root, "objectbank", ident=f"bank_{bank_ident}")
    f = SubElement(SubElement(ob, "qtimetadata"), "qtimetadatafield")
    SubElement(f, "fieldlabel").text = "bank_title"
    SubElement(f, "fieldentry").text = bank["title"]

    for q in bank["questions"]:
        try:
            ob.append(question_to_qti_item(q))
        except Exception as e:
            print(f"    Warning: Skipping Q {q.get('id')} ({q.get('question_type')}): {e}")

    return root


def export_qti(banks, qti_dir):
    for bank in banks:
        safe_title = re.sub(r"[^\w\s-]", "", bank["title"]).strip().replace(" ", "_")[:50]
        filename = f"bank_{re.sub(r'[^a-zA-Z0-9_]', '_', str(bank['id']))}_{safe_title}.xml"
        path = qti_dir / filename
        root = bank_to_qti_root(bank)
        path.write_text(_pretty_xml(root), encoding="utf-8")
        print(f"  QTI: {filename}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Canvas URL:  {CANVAS_URL}")
    print(f"Course ID:   {COURSE_ID}")
    print()

    # --- Detect API type and fetch banks ---
    api_type = None
    banks = []

    print("Trying Classic Quizzes API...")
    try:
        raw_banks = classic_get_banks(COURSE_ID)
        if raw_banks:
            api_type = "classic"
            print(f"  Found {len(raw_banks)} bank(s) via Classic Quizzes API\n")
            for rb in raw_banks:
                print(f"  [{rb['id']}] {rb['title']}")
                questions = classic_get_questions(rb["id"])
                rb["questions"] = questions
                rb["_api_type"] = "classic"
                print(f"    -> {len(questions)} questions")
            banks = raw_banks
        else:
            print("  No banks returned (course may use New Quizzes).")
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            print(f"  Classic API returned 404 — course likely uses New Quizzes.")
        else:
            print(f"  Classic API error: {e}")

    if not banks:
        print("\nTrying New Quizzes API...")
        try:
            raw_banks = nq_get_banks(COURSE_ID)
            if raw_banks:
                api_type = "new_quizzes"
                print(f"  Found {len(raw_banks)} bank(s) via New Quizzes API\n")
                for rb in raw_banks:
                    title = rb.get("title", rb.get("name", "(Untitled)"))
                    bid = rb.get("id", "")
                    print(f"  [{bid}] {title}")
                    items = nq_get_items(bid)
                    bank = nq_normalize_bank(rb, items)
                    print(f"    -> {len(bank['questions'])} questions")
                    banks.append(bank)
            else:
                print("  No banks found via New Quizzes API either.")
        except requests.exceptions.HTTPError as e:
            print(f"  New Quizzes API error: {e}")

    if not banks:
        print(
            "\nNo question banks found for this course.\n"
            "Possible reasons:\n"
            "  - The course has no question banks\n"
            "  - Your token lacks permission to view item banks\n"
            "  - The course uses a quiz engine not yet supported\n"
            "  - The COURSE_ID is for a different Canvas instance"
        )
        sys.exit(0)

    print(f"\nAPI: {api_type} | Total banks: {len(banks)}")

    # --- Create output directory ---
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"export_course_{COURSE_ID}_{stamp}")
    qti_dir = out_dir / "qti"
    out_dir.mkdir(exist_ok=True)
    qti_dir.mkdir(exist_ok=True)

    # JSON
    json_path = out_dir / "item_banks.json"
    json_path.write_text(
        json.dumps(
            {
                "export_date": datetime.now().isoformat(),
                "course_id": COURSE_ID,
                "canvas_url": CANVAS_URL,
                "api_type": api_type,
                "banks": banks,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nJSON  -> {json_path}")

    # Markdown
    md_path = out_dir / "item_banks.md"
    export_markdown(banks, COURSE_ID, md_path)
    print(f"MD    -> {md_path}")

    # QTI
    print("QTI   -> exporting...")
    export_qti(banks, qti_dir)

    print(f"\nDone. Output folder: {out_dir}/")
    print()
    print("Next steps:")
    print(f"  1. Upload '{md_path}' to claude.ai and ask Claude to reorganize/edit.")
    print(f"  2. Have Claude output a revised Markdown in the same format.")
    print(f"  3. Import QTI files from '{qti_dir}/' via:")
    print(f"     Course Settings > Import Course Content > QTI .zip file")


if __name__ == "__main__":
    main()
