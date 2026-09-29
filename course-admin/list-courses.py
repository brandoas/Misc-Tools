"""List all courses visible to the token owner, with IDs and terms.

Usage: python list-courses.py [search-string]
Example: python list-courses.py 4750
"""

import sys

from canvas_api import get_paginated

search = sys.argv[1].lower() if len(sys.argv) > 1 else None

courses = get_paginated(
    "/api/v1/courses",
    {"include[]": "term", "state[]": ["unpublished", "available", "completed"]},
)

for c in courses:
    name = c.get("name") or "(unnamed)"
    if search and search not in name.lower() and search not in str(c["id"]):
        continue
    term = (c.get("term") or {}).get("name", "")
    state = c.get("workflow_state", "")
    print(f"{c['id']:>8}  {state:<12} {term:<20} {name}")
