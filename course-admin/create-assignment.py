"""Create (or preview) a single assignment in a Canvas course.

Companion to put-rubric.py. Creates the assignment UNPUBLISHED by default so it
can be reviewed before students see it. Dry run by default: prints the fields it
would POST and exits. Re-run with --apply to create it.

Usage:
    python create-assignment.py COURSE_ID --name "Deliverable 2: ..." \
        --points 100 --description-file brief.html \
        [--submission online_upload] [--ext pdf] [--group GROUP_ID] \
        [--publish] [--apply]

Notes:
- --publish is off by default; without it the assignment is created unpublished.
- --description-file is an HTML fragment used as the assignment description.
- Prints the new assignment id on success (feed it to put-rubric.py).
"""

import sys

import coursekit as ck


def arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


def main(argv):
    if len(argv) < 1 or argv[0].startswith("--"):
        sys.exit(__doc__)
    course_id = argv[0]
    apply_changes = "--apply" in argv
    name = arg(argv, "--name")
    points = arg(argv, "--points", "0")
    desc_file = arg(argv, "--description-file")
    submission = arg(argv, "--submission", "online_upload")
    ext = arg(argv, "--ext", "pdf")
    group = arg(argv, "--group")
    published = "--publish" in argv
    if not name:
        sys.exit("ERROR: --name is required.")

    description = ""
    if desc_file:
        with open(desc_file, encoding="utf-8") as fh:
            description = fh.read()

    course = ck.get(f"/api/v1/courses/{course_id}")
    print(f"Course {course_id}: {course.get('name')}")
    print(f"Assignment: {name}")
    print(f"  points_possible : {points}")
    print(f"  submission_types: {submission}")
    print(f"  allowed_extensions: {ext}")
    print(f"  published       : {published}")
    print(f"  description     : {len(description)} chars from {desc_file or '(none)'}")

    data = {
        "assignment[name]": name,
        "assignment[points_possible]": points,
        "assignment[submission_types][]": submission,
        "assignment[published]": str(published).lower(),
        "assignment[description]": description,
    }
    if submission == "online_upload" and ext:
        data["assignment[allowed_extensions][]"] = ext
    if group:
        data["assignment[assignment_group_id]"] = group

    if not apply_changes:
        print("\nDRY RUN (add --apply to create)")
        return

    r = ck.requests.post(
        f"{ck.BASE_URL}/api/v1/courses/{course_id}/assignments",
        headers=ck.HEADERS, data=data)
    r.raise_for_status()
    out = r.json()
    print(f"\nCreated assignment {out['id']} ('{out['name']}'), "
          f"published={out['published']}.")
    print(f"Attach the rubric with:\n"
          f"  python put-rubric.py profiles/rubrics/deliverable-02.json "
          f"{course_id} {out['id']} --apply")


if __name__ == "__main__":
    main(sys.argv[1:])
