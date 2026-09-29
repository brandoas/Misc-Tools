"""Download a course's Canvas Syllabus page body as HTML.

Usage: python get-syllabus.py COURSE_ID [output.html]
"""

import sys

from canvas_api import get

if len(sys.argv) < 2:
    sys.exit("Usage: python get-syllabus.py COURSE_ID [output.html]")

course_id = sys.argv[1]
outfile = sys.argv[2] if len(sys.argv) > 2 else f"syllabus-{course_id}.html"

course = get(f"/api/v1/courses/{course_id}", {"include[]": "syllabus_body"})

body = course.get("syllabus_body") or ""
with open(outfile, "w", encoding="utf-8") as f:
    f.write(body)

print(f"Course: {course.get('name')}")
print(f"Saved {len(body)} characters of syllabus HTML to {outfile}")
