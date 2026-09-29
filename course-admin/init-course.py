"""Initialize (or re-check) a Canvas course against a course profile.

Applies navigation, course settings, feature flags, and starter items from a
profile JSON in one pass. Dry run by default: prints every change it would
make and exits. Re-run with --apply to execute, then run again without
--apply to confirm zero drift.

Usage:
    python init-course.py profiles/4750.json COURSE_ID [--term-start YYYY-MM-DD] [--apply]
    python init-course.py profiles/4750.json COURSE_ID --only navigation,features

--term-start is the first day of classes. It is required only if the profile
has starter items with relative due dates. --only limits the pass to the named
sections (navigation, settings, features, starters).

Never touches grades, submissions, or People.
"""

import sys

import coursekit as ck


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    profile_path, course_id = argv[0], argv[1]
    apply_changes = "--apply" in argv
    term_start = None
    only = None
    for i, a in enumerate(argv):
        if a == "--term-start":
            term_start = ck.parse_date(argv[i + 1])
        if a == "--only":
            only = set(argv[i + 1].split(","))

    profile = ck.load_profile(profile_path)
    if only:
        keep = {"navigation": "navigation", "settings": "settings", "course": "settings",
                "features": "features", "gradebook": "gradebook", "starter_items": "starters"}
        profile = {k: v for k, v in profile.items() if keep.get(k) in only or k == "name"}

    course = ck.get(f"/api/v1/courses/{course_id}")
    print(f"Course {course_id}: {course.get('name')}")
    print(f"Profile: {profile.get('name', profile_path)}")

    changes = ck.plan_all(course_id, profile, term_start)
    if not changes:
        print("\nCourse already matches the profile. Nothing to do.")
        return

    mode = "APPLYING" if apply_changes else "DRY RUN (add --apply to execute)"
    print(f"\n{mode}: {len(changes)} change(s)\n")
    for c in changes:
        print(c.describe())
        if apply_changes:
            try:
                c.run()
            except Exception as e:
                print(f"    WARN: failed: {e}")
    if apply_changes:
        print("\nDone. Re-run without --apply to verify zero remaining changes.")


if __name__ == "__main__":
    main(sys.argv[1:])
