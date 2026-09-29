"""Course configuration library for Canvas-Tools.

A *course profile* is a JSON file describing how a course should be set up.
Every section is optional; anything not mentioned is left alone.

    {
      "name": "ITS 4750",
      "navigation": {"visible": ["syllabus", "modules", "LTI: Library Resources", ...]},
      "settings":   {"default_due_time": "17:00:00", "syllabus_course_summary": true},
      "course":     {"default_view": "modules"},
      "features":   {"quizzes_next": "on", "new_quizzes_by_default": "on"},
      "starter_items": [
        {
          "type": "new_quiz",
          "title": "GitHub ID",
          "instructions": "<p>...</p>",
          "points_possible": 0,
          "due": {"offset_days": 0, "time": "default"},
          "unlimited_attempts": true,
          "questions": [{"type": "essay", "title": "GitHub ID", "body": "<p>What is your GitHub ID?</p>"}]
        }
      ]
    }

Each section exposes plan_*(course_id, profile_section, ...) returning a list
of Change objects, and apply_change(change) to execute one. Scripts decide
whether to print (dry run) or apply.

"due" for starter items is relative to a term start date supplied by the
caller (--term-start YYYY-MM-DD), since OU terms carry no start_at in the API.
"time" is either "default" (the course's default_due_time) or "HH:MM:SS".
Times are interpreted in the course time zone (America/New_York at OU).

Scope rule: nothing in here reads or writes grades, submissions, or People.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from canvas_api import BASE_URL, HEADERS, get, get_paginated, put

# ---------------------------------------------------------------- helpers


@dataclass
class Change:
    section: str
    action: str          # short verb: show / hide / move / set / enable / create
    target: str          # what is being changed
    have: object = None
    want: object = None
    run: object = None   # zero-arg callable that performs the change

    def describe(self):
        if self.have is None and self.want is None:
            return f"  {self.section:10} {self.action:7} {self.target}"
        return f"  {self.section:10} {self.action:7} {self.target}: {self.have!r} -> {self.want!r}"


def _json_put(path, payload):
    r = requests.put(f"{BASE_URL}{path}", headers={**HEADERS, "Content-Type": "application/json"}, json=payload)
    r.raise_for_status()
    return r.json()


def _json_post(path, payload):
    r = requests.post(f"{BASE_URL}{path}", headers={**HEADERS, "Content-Type": "application/json"}, json=payload)
    r.raise_for_status()
    return r.json()


def load_profile(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------- navigation

# home and settings cannot be hidden; accessibility is the institution-pinned
# instructor tab OU added in Spring 26 courses, so leave it as Canvas set it.
UNMANAGEABLE_TABS = {"home", "settings", "accessibility"}


def tab_key(tab):
    if tab["id"].startswith("context_external_tool"):
        return f"LTI: {tab.get('label')}"
    return tab["id"]


def load_tabs(course_id):
    return get_paginated(f"/api/v1/courses/{course_id}/tabs")


def dump_navigation(course_id):
    tabs = load_tabs(course_id)
    return {
        "visible": [
            tab_key(t)
            for t in sorted(tabs, key=lambda t: t.get("position", 99))
            if not t.get("hidden") and t["id"] not in UNMANAGEABLE_TABS
        ]
    }


def plan_navigation(course_id, nav):
    visible = nav["visible"]
    tabs = load_tabs(course_id)
    by_key = {tab_key(t): t for t in tabs}
    changes = []

    for k in visible:
        if k not in by_key:
            print(f"WARN: nav element '{k}' not found in course {course_id}; skipping")

    def updater(tab, data):
        return lambda: put(f"/api/v1/courses/{course_id}/tabs/{tab['id']}", data)

    pos = 2  # position 1 is Home
    for k in visible:
        t = by_key.get(k)
        if not t or t["id"] in UNMANAGEABLE_TABS:
            continue
        hidden_now = bool(t.get("hidden"))
        pos_now = t.get("position")
        if hidden_now:
            changes.append(Change("navigation", "show", k, "hidden", f"position {pos}",
                                  updater(t, {"hidden": "false", "position": pos})))
        elif pos_now != pos:
            changes.append(Change("navigation", "move", k, pos_now, pos,
                                  updater(t, {"hidden": "false", "position": pos})))
        pos += 1

    wanted = set(visible)
    for k, t in by_key.items():
        if t["id"] in UNMANAGEABLE_TABS or k in wanted:
            continue
        if not t.get("hidden"):
            changes.append(Change("navigation", "hide", k, "visible", "hidden",
                                  updater(t, {"hidden": "true"})))
    return changes


# --------------------------------------------------------------- settings

# Fields that live on the course object rather than /settings.
COURSE_FIELDS = {"default_view", "license", "is_public", "public_syllabus",
                 "apply_assignment_group_weights", "time_zone", "grading_standard_id",
                 "hide_final_grades"}

DUMP_SETTINGS = ["default_due_time", "allow_final_grade_override", "syllabus_course_summary", "lock_all_announcements",
                 "show_announcements_on_home_page", "home_page_announcement_limit",
                 "allow_student_discussion_topics", "allow_student_discussion_editing",
                 "allow_student_organized_groups", "restrict_student_past_view",
                 "restrict_student_future_view", "hide_distribution_graphs",
                 "grading_standard_enabled", "usage_rights_required"]
DUMP_COURSE = ["default_view", "apply_assignment_group_weights", "public_syllabus", "time_zone"]


def dump_settings(course_id):
    s = get(f"/api/v1/courses/{course_id}/settings")
    c = get(f"/api/v1/courses/{course_id}")
    return ({k: s.get(k) for k in DUMP_SETTINGS if k in s},
            {k: c.get(k) for k in DUMP_COURSE if k in c})


def plan_settings(course_id, settings=None, course=None):
    changes = []
    if settings:
        have = get(f"/api/v1/courses/{course_id}/settings")
        for k, want in settings.items():
            if have.get(k) != want:
                changes.append(Change("settings", "set", k, have.get(k), want,
                                      lambda k=k, want=want: _json_put(f"/api/v1/courses/{course_id}/settings", {k: want})))
    if course:
        have = get(f"/api/v1/courses/{course_id}")
        for k, want in course.items():
            if have.get(k) != want:
                changes.append(Change("course", "set", k, have.get(k), want,
                                      lambda k=k, want=want: _json_put(f"/api/v1/courses/{course_id}", {"course": {k: want}})))
    return changes


# --------------------------------------------------------------- features


def load_features(course_id):
    feats = get_paginated(f"/api/v1/courses/{course_id}/features")
    return {f["feature"]: f for f in feats}


def dump_features(course_id):
    """Only flags explicitly set at the course level (on/off), not inherited."""
    out = {}
    for name, f in load_features(course_id).items():
        flag = f["feature_flag"]
        if flag.get("locked"):
            continue
        if flag.get("context_type") == "Course" and flag["state"] in ("on", "off"):
            out[name] = flag["state"]
    return out


def plan_features(course_id, features):
    feats = load_features(course_id)
    changes = []
    for name, want in features.items():
        f = feats.get(name)
        if not f:
            print(f"WARN: feature '{name}' not available in course {course_id}; skipping")
            continue
        flag = f["feature_flag"]
        if flag.get("locked"):
            print(f"WARN: feature '{name}' is locked by the institution; skipping")
            continue
        have = flag["state"]
        # "allowed_on" means inherited on; treat as already on.
        effective = "on" if have in ("on", "allowed_on") else have
        if effective != want:
            label = f.get("display_name") or name
            changes.append(Change("features", "set", f"{name} ({label})", have, want,
                                  lambda name=name, want=want: _json_put(f"/api/v1/courses/{course_id}/features/flags/{name}", {"state": want})))
    return changes


# -------------------------------------------------------------- gradebook

# Late/missing policy via the documented Late Policy API. The view settings
# go through the new-gradebook settings endpoint; they are stored per user
# per course, so they configure the gradebook as the token owner sees it.
# NOT settable via API (one-time clicks in the gradebook View menu):
# Arrange By > Due Date (newest first), and the status icons toggle.

GB_VIEW_KEYS = ("show_unpublished_assignments", "show_separate_first_last_names",
                "hide_assignment_group_totals")


def get_late_policy(course_id):
    r = requests.get(f"{BASE_URL}/api/v1/courses/{course_id}/late_policy", headers=HEADERS)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()["late_policy"]


def plan_gradebook(course_id, gb):
    changes = []
    want_lp = gb.get("late_policy")
    if want_lp:
        have = get_late_policy(course_id)

        def apply_lp():
            if get_late_policy(course_id) is None:
                r = requests.post(f"{BASE_URL}/api/v1/courses/{course_id}/late_policy",
                                  headers={**HEADERS, "Content-Type": "application/json"},
                                  json={"late_policy": want_lp})
            else:
                r = requests.patch(f"{BASE_URL}/api/v1/courses/{course_id}/late_policy",
                                   headers={**HEADERS, "Content-Type": "application/json"},
                                   json={"late_policy": want_lp})
            r.raise_for_status()

        if have is None:
            changes.append(Change("gradebook", "create", "late policy", None, want_lp, apply_lp))
        else:
            diffs = {k: (have.get(k), v) for k, v in want_lp.items() if have.get(k) != v}
            if diffs:
                changes.append(Change("gradebook", "set", "late policy", {k: d[0] for k, d in diffs.items()},
                                      {k: d[1] for k, d in diffs.items()}, apply_lp))

    view = {k: str(gb[k]).lower() for k in GB_VIEW_KEYS if k in gb}
    if view:
        def apply_view():
            r = requests.put(f"{BASE_URL}/api/v1/courses/{course_id}/gradebook_settings",
                             headers={**HEADERS, "Content-Type": "application/json"},
                             json={"gradebook_settings": view})
            r.raise_for_status()
        # No GET for these; apply idempotently whenever the profile lists them.
        changes.append(Change("gradebook", "set", "view settings (per user)", None, view, apply_view))
    return changes


# ----------------------------------------------------------- starter items

COURSE_TZ = ZoneInfo("America/New_York")


def resolve_due(due, term_start, default_due_time):
    """due = {"offset_days": N, "time": "default" | "HH:MM:SS"} -> ISO UTC string."""
    if due is None:
        return None
    if isinstance(due, str):
        return due  # already an ISO timestamp
    if term_start is None:
        raise SystemExit("starter item has a relative due date but no --term-start was given")
    d = term_start + timedelta(days=due.get("offset_days", 0))
    t = due.get("time", "default")
    if t == "default":
        t = default_due_time or "23:59:59"
    hh, mm, ss = (int(x) for x in t.split(":"))
    local = datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=COURSE_TZ)
    return local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def _essay_item(q, position):
    return {"item": {
        "entry_type": "Item", "points_possible": q.get("points", 0), "position": position,
        "entry": {
            "title": q.get("title", f"Question {position}"),
            "item_body": q["body"],
            "interaction_type_slug": "essay",
            "interaction_data": {"rce": q.get("rce", False), "essay": None, "word_count": False,
                                  "file_upload": False, "spell_check": False,
                                  "word_limit_enabled": False, "show_word_count": False},
            "scoring_data": {"value": ""}, "scoring_algorithm": "None", "properties": {},
        }}}


def _create_new_quiz(course_id, item, due_at):
    quiz = {
        "title": item["title"],
        "instructions": item.get("instructions", ""),
        "points_possible": item.get("points_possible", 0),
        "grading_type": "points",
    }
    if due_at:
        quiz["due_at"] = due_at
    if item.get("unlimited_attempts"):
        quiz["quiz_settings"] = {"multiple_attempts": {
            "multiple_attempts_enabled": True, "attempt_limit": False, "score_to_keep": "latest"}}
    created = _json_post(f"/api/quiz/v1/courses/{course_id}/quizzes", {"quiz": quiz})
    aid = created["id"]
    for i, q in enumerate(item.get("questions", []), start=1):
        if q.get("type", "essay") != "essay":
            raise SystemExit(f"question type '{q['type']}' not supported yet")
        _json_post(f"/api/quiz/v1/courses/{course_id}/quizzes/{aid}/items", _essay_item(q, i))
    if item.get("published", True):
        _json_put(f"/api/v1/courses/{course_id}/assignments/{aid}", {"assignment": {"published": True}})
    return aid


def plan_starter_items(course_id, items, term_start=None):
    if not items:
        return []
    existing = {a["name"] for a in get_paginated(f"/api/v1/courses/{course_id}/assignments")}
    default_due = get(f"/api/v1/courses/{course_id}/settings").get("default_due_time")
    changes = []
    for item in items:
        if item["title"] in existing:
            continue
        if item.get("type", "new_quiz") != "new_quiz":
            print(f"WARN: starter item type '{item.get('type')}' not supported; skipping")
            continue
        due_at = resolve_due(item.get("due"), term_start, default_due)
        changes.append(Change("starters", "create", f"New Quiz '{item['title']}' due {due_at}",
                              run=lambda item=item, due_at=due_at: _create_new_quiz(course_id, item, due_at)))
    return changes


# ------------------------------------------------------------------ driver


def plan_all(course_id, profile, term_start=None):
    changes = []
    if "navigation" in profile:
        changes += plan_navigation(course_id, profile["navigation"])
    if "settings" in profile or "course" in profile:
        changes += plan_settings(course_id, profile.get("settings"), profile.get("course"))
    if "features" in profile:
        changes += plan_features(course_id, profile["features"])
    if "gradebook" in profile:
        changes += plan_gradebook(course_id, profile["gradebook"])
    if "starter_items" in profile:
        changes += plan_starter_items(course_id, profile["starter_items"], term_start)
    return changes


def parse_date(s):
    return date.fromisoformat(s)
