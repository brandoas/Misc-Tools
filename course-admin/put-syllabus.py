"""Upload an HTML file as a course's Canvas Syllabus page body.

Usage: python put-syllabus.py COURSE_ID input.html

Downloads the current syllabus to a backup file first
(syllabus-COURSE_ID-backup.html) so the change is reversible.
"""

import sys

from canvas_api import get, put

if len(sys.argv) < 3:
    sys.exit("Usage: python put-syllabus.py COURSE_ID input.html")

course_id = sys.argv[1]
infile = sys.argv[2]

with open(infile, "r", encoding="utf-8") as f:
    new_body = f.read()

# Back up whatever is there now
course = get(f"/api/v1/courses/{course_id}", {"include[]": "syllabus_body"})
backup = f"syllabus-{course_id}-backup.html"
with open(backup, "w", encoding="utf-8") as f:
    f.write(course.get("syllabus_body") or "")
print(f"Backed up current syllabus to {backup}")

result = put(f"/api/v1/courses/{course_id}", {"course[syllabus_body]": new_body})
print(f"Updated syllabus for course {result['id']}: {result.get('name')}")
