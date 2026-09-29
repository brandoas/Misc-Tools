"""List a course's Modules with their items.

Usage:
    python list-modules.py COURSE_ID            # human-readable
    python list-modules.py COURSE_ID out.json   # also save full JSON
"""

import json
import sys

from canvas_api import get_paginated

if len(sys.argv) < 2:
    sys.exit("Usage: python list-modules.py COURSE_ID [out.json]")

course_id = sys.argv[1]
mods = get_paginated(
    f"/api/v1/courses/{course_id}/modules", {"include[]": "items"}
)

for m in mods:
    pub = "published" if m.get("published") else "UNPUBLISHED"
    print(f"{m.get('position'):>2}. [{pub}] {m.get('name')}")
    for it in m.get("items") or []:
        indent = "      " + "  " * it.get("indent", 0)
        print(f"{indent}- ({it.get('type')}) {it.get('title')}")

if len(sys.argv) > 2:
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(mods, f, indent=2)
    print(f"\nSaved full module JSON to {sys.argv[2]}")
