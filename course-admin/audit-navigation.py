"""Audit course navigation (Settings > Navigation) across multiple courses.

For each course, pulls the Canvas tabs API and reports which navigation
elements are enabled (visible to students) and which are hidden. Then
classifies every element across the whole set:

    ALWAYS ON   enabled in every audited course
    ALWAYS OFF  hidden in every audited course
    VARIES      enabled in some courses, hidden in others

Usage:
    python audit-navigation.py COURSE_ID [COURSE_ID ...]
    python audit-navigation.py --json out.json COURSE_ID [COURSE_ID ...]

Notes on the tabs API: every tab has an id (e.g. "home", "syllabus", or
"context_external_tool_NNN" for LTI tools), a label, a position, and an
optional hidden flag. hidden=true means the element is unchecked in the
Navigation settings (students don't see it). The "home" and "settings"
tabs cannot be hidden; settings is teacher-only by nature.
"""

import json
import sys

from canvas_api import get, get_paginated

args = [a for a in sys.argv[1:]]
json_out = None
if "--json" in args:
    i = args.index("--json")
    json_out = args[i + 1]
    del args[i : i + 2]

if not args:
    sys.exit("Usage: python audit-navigation.py [--json out.json] COURSE_ID ...")

courses = {}
for cid in args:
    info = get(f"/api/v1/courses/{cid}")
    tabs = get_paginated(f"/api/v1/courses/{cid}/tabs")
    courses[cid] = {"name": info.get("name"), "tabs": tabs}
    print(f"\n=== {cid}  {info.get('name')}")
    for t in sorted(tabs, key=lambda t: t.get("position", 99)):
        state = "OFF" if t.get("hidden") else "on "
        print(f"  {state}  pos {t.get('position'):>2}  {t['id']:<38} {t.get('label')}")

# Cross-course classification, keyed by tab id (label shown for readability).
# LTI tools get different ids per course, so key those by label instead.
def key_of(tab):
    if tab["id"].startswith("context_external_tool"):
        return f"LTI: {tab.get('label')}"
    return tab["id"]

matrix = {}
for cid, c in courses.items():
    for t in c["tabs"]:
        k = key_of(t)
        matrix.setdefault(k, {"label": t.get("label"), "states": {}})
        matrix[k]["states"][cid] = not t.get("hidden")

n = len(courses)
always_on, always_off, varies = [], [], []
for k, m in sorted(matrix.items()):
    states = m["states"]
    on_count = sum(states.values())
    present = len(states)
    entry = (k, m["label"], on_count, present)
    if on_count == present == n:
        always_on.append(entry)
    elif on_count == 0 and present == n:
        always_off.append(entry)
    else:
        varies.append(entry)

def show(title, entries):
    print(f"\n--- {title} ({len(entries)})")
    for k, label, on_count, present in entries:
        extra = "" if present == n else f"  [only in {present}/{n} courses]"
        print(f"  {k:<44} on in {on_count}/{present}{extra}")

print(f"\n================ ANALYSIS ACROSS {n} COURSES ================")
show("ALWAYS ON", always_on)
show("ALWAYS OFF", always_off)
show("VARIES / NOT UNIVERSAL", varies)

if json_out:
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump({"courses": courses, "matrix": matrix}, f, indent=2)
    print(f"\nRaw data saved to {json_out}")
