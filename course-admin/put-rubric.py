"""Create a rubric in a course from a JSON file and attach it to an assignment.

Usage:
    python put-rubric.py RUBRIC.json COURSE_ID ASSIGNMENT_ID [--apply]

Rubric JSON (see <course repo>/Grading/Rubric/):
    {
      "title": "Lab 01 - DDI",
      "free_form_criterion_comments": false,
      "criteria": [
        {"description": "...", "long_description": "...", "points": 25,
         "ratings": [{"description": "Complete", "long_description": "...", "points": 25}, ...]}
      ]
    }

Dry run prints the criteria and points. --apply creates the rubric and the
assignment association (use_for_grading=true). Canvas allows one rubric per
assignment; if one is already attached this script refuses rather than
replacing it.
"""

import sys

import coursekit as ck


def form_encode(rubric):
    """Canvas rubric create wants nested form params, not JSON."""
    data = {
        "rubric[title]": rubric["title"],
        "rubric[free_form_criterion_comments]": str(rubric.get("free_form_criterion_comments", False)).lower(),
    }
    for i, c in enumerate(rubric["criteria"]):
        p = f"rubric[criteria][{i}]"
        data[f"{p}[description]"] = c["description"]
        data[f"{p}[long_description]"] = c.get("long_description", "")
        data[f"{p}[points]"] = c["points"]
        data[f"{p}[criterion_use_range]"] = "false"
        for j, r in enumerate(c["ratings"]):
            q = f"{p}[ratings][{j}]"
            data[f"{q}[description]"] = r["description"]
            data[f"{q}[long_description]"] = r.get("long_description", "")
            data[f"{q}[points]"] = r["points"]
    return data


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    path, course_id, assignment_id = argv[0], argv[1], argv[2]
    apply_changes = "--apply" in argv
    rubric = ck.load_profile(path)
    total = sum(c["points"] for c in rubric["criteria"])

    a = ck.get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")
    print(f"Assignment {assignment_id}: {a['name']} ({a['points_possible']} pts)")
    if a.get("rubric"):
        sys.exit(f"Refusing: assignment already has rubric '{a.get('rubric_settings', {}).get('title')}'. Remove it in Canvas first.")
    print(f"Rubric '{rubric['title']}': {len(rubric['criteria'])} criteria, {total} pts")
    for c in rubric["criteria"]:
        print(f"  [{c['points']:>3}] {c['description']}")
    if total != a["points_possible"]:
        print(f"WARN: rubric total {total} != assignment points {a['points_possible']}")
    if not apply_changes:
        print("\nDRY RUN (add --apply to create)")
        return

    data = form_encode(rubric)
    data.update({
        "rubric_association[association_type]": "Assignment",
        "rubric_association[association_id]": assignment_id,
        "rubric_association[use_for_grading]": "true",
        "rubric_association[purpose]": "grading",
    })
    r = ck.requests.post(f"{ck.BASE_URL}/api/v1/courses/{course_id}/rubrics", headers=ck.HEADERS, data=data)
    r.raise_for_status()
    out = r.json()
    print(f"\nCreated rubric {out['rubric']['id']} and attached it to assignment {assignment_id}.")


if __name__ == "__main__":
    main(sys.argv[1:])
