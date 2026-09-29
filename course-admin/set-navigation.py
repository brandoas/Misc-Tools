"""Set a course's navigation (Settings > Navigation) from a JSON profile.

Thin wrapper over coursekit for nav-only work. For the full course setup
(nav + settings + features + starter items) use init-course.py.

Usage:
    python set-navigation.py PROFILE.json COURSE_ID           # dry run (default)
    python set-navigation.py PROFILE.json COURSE_ID --apply   # make the changes
    python set-navigation.py --dump COURSE_ID                 # print a nav profile

PROFILE.json may be a bare nav profile ({"visible": [...]}) or a full course
profile from profiles/ (its "navigation" section is used).

"visible" lists the elements students should see, in menu order. Built-in
tabs are named by their Canvas id (syllabus, modules, assignments, ...).
External (LTI) tools are named "LTI: <label>" because their tab ids differ
per course. Every hideable element NOT in the list is hidden. home and
settings are managed by Canvas; accessibility is institution-pinned.
"""

import json
import sys

import coursekit as ck


def main(argv):
    if not argv:
        sys.exit(__doc__)
    if argv[0] == "--dump":
        print(json.dumps(ck.dump_navigation(argv[1]), indent=2))
        return
    profile = ck.load_profile(argv[0])
    nav = profile.get("navigation", profile)
    course_id = argv[1]
    apply_changes = "--apply" in argv
    changes = ck.plan_navigation(course_id, nav)
    if not changes:
        print("Navigation already matches the profile. Nothing to do.")
        return
    mode = "APPLYING" if apply_changes else "DRY RUN (use --apply to execute)"
    print(f"\n{mode}: {len(changes)} change(s) for course {course_id}\n")
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
