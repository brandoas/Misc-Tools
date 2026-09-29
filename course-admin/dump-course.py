"""Build a course profile JSON from an existing Canvas course.

Captures navigation (visible tabs in order), the course settings we manage,
and feature flags explicitly set at the course level. Starter items are not
inferred; add them to the profile by hand.

Usage:
    python dump-course.py COURSE_ID [--name "ITS 3100"] > profiles/3100.json

Use this at the end of a semester that went well: the dump becomes next
year's template for init-course.py.
"""

import json
import sys

import coursekit as ck


def main(argv):
    if not argv:
        sys.exit(__doc__)
    course_id = argv[0]
    name = None
    if "--name" in argv:
        name = argv[argv.index("--name") + 1]
    course = ck.get(f"/api/v1/courses/{course_id}")
    settings, course_fields = ck.dump_settings(course_id)
    profile = {
        "name": name or course.get("name"),
        "source_course_id": int(course_id),
        "navigation": ck.dump_navigation(course_id),
        "settings": settings,
        "course": course_fields,
        "features": ck.dump_features(course_id),
        "starter_items": [],
    }
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
