"""Post ITS-4750 Deliverable 04 (Ansible Automation) to Canvas.

Run from Misc-Tools/course-admin (reads the Canvas token from ../.env via
coursekit). Dry-run by default; add --apply to create the three assignments,
attach their rubrics, set due dates, and PUBLISH.

    python3 post-d04.py            # preview
    python3 post-d04.py --apply    # create + date + publish

Reads its inputs from ITS-4750-Infrastructure/Grading/Rubric/: 4750-d04-*-description.html,
4750-d04-prelab.json, 4750-d04-grader.json, weekly-faculty-v2.json.

Notes:
- docx submission, group 170654 (Weekly Labs), split 10/75/15.
- Grader rubric totals 80 on a 75-point assignment: the extra 5 is the Task 9
  OSPFv3 bonus criterion. put-rubric-style mismatch is intentional.
- Faculty uses a NEW shared rubric "Weekly Faculty v2" (created here); its id is
  printed so later deliverables can reuse it via a rubric_association instead of
  recreating it.
- Plagiarism review (Turnitin, report hidden) is a manual UI step per assignment;
  this script cannot set it.
"""

import sys, json
from pathlib import Path
import coursekit as ck

COURSE = "82426"
GROUP = "170654"
RB = str(Path(__file__).resolve().parent.parent.parent / "ITS-4750-Infrastructure" / "Grading" / "Rubric") + "/"
APPLY = "--apply" in sys.argv

PLAN = [
    ("Deliverable 04 - PreLab",  10, "4750-d04-prelab-description.html",  "4750-d04-prelab.json",       "2026-09-15T13:00:00Z"),
    ("Deliverable 04 - Grader",  75, "4750-d04-grader-description.html",  "4750-d04-grader.json",       "2026-09-22T21:00:00Z"),
    ("Deliverable 04 - Faculty", 15, "4750-d04-faculty-description.html", "weekly-faculty-v2.json","2026-09-22T21:00:00Z"),
]


def _post(path, data):
    r = ck.requests.post(f"{ck.BASE_URL}{path}", headers=ck.HEADERS, data=data); r.raise_for_status(); return r.json()


def _put(path, data):
    r = ck.requests.put(f"{ck.BASE_URL}{path}", headers=ck.HEADERS, data=data); r.raise_for_status(); return r.json()


def rubric_form(rub):
    d = {"rubric[title]": rub["title"], "rubric[free_form_criterion_comments]": "false"}
    for i, c in enumerate(rub["criteria"]):
        p = f"rubric[criteria][{i}]"
        d[f"{p}[description]"] = c["description"]
        d[f"{p}[long_description]"] = c.get("long_description", "")
        d[f"{p}[points]"] = c["points"]
        d[f"{p}[criterion_use_range]"] = "false"
        for j, rt in enumerate(c["ratings"]):
            q = f"{p}[ratings][{j}]"
            d[f"{q}[description]"] = rt["description"]
            d[f"{q}[long_description]"] = rt.get("long_description", "")
            d[f"{q}[points]"] = rt["points"]
    return d


def main():
    if not APPLY:
        print(f"DRY RUN - would post to course {COURSE}, group {GROUP} (docx, then publish):\n")
        for name, pts, desc, rub, due in PLAN:
            r = json.load(open(RB + rub))
            tot = sum(c["points"] for c in r["criteria"])
            flag = "  (rubric 80 on 75 = 5 bonus)" if tot != pts else ""
            print(f"  {name}: {pts} pts, due {due}")
            print(f"      rubric '{r['title']}' - {len(r['criteria'])} crit, {tot} pts{flag}")
        print("\nRe-run with --apply to create, date, and publish.")
        return

    for name, pts, desc, rub, due in PLAN:
        html = open(RB + desc, encoding="utf-8").read()
        a = _post(f"/api/v1/courses/{COURSE}/assignments", {
            "assignment[name]": name,
            "assignment[points_possible]": pts,
            "assignment[submission_types][]": "online_upload",
            "assignment[allowed_extensions][]": "docx",
            "assignment[published]": "false",
            "assignment[description]": html,
            "assignment[assignment_group_id]": GROUP,
        })
        aid = a["id"]
        data = rubric_form(json.load(open(RB + rub)))
        data.update({
            "rubric_association[association_type]": "Assignment",
            "rubric_association[association_id]": aid,
            "rubric_association[use_for_grading]": "true",
            "rubric_association[purpose]": "grading",
        })
        rid = _post(f"/api/v1/courses/{COURSE}/rubrics", data)["rubric"]["id"]
        _put(f"/api/v1/courses/{COURSE}/assignments/{aid}", {"assignment[due_at]": due})
        _put(f"/api/v1/courses/{COURSE}/assignments/{aid}", {"assignment[published]": "true"})
        print(f"posted {name}: assignment {aid}, rubric {rid}, due {due}, published")

    print("\nDONE. Two follow-ups:")
    print(" 1. In Canvas UI, enable Turnitin plagiarism review with the report hidden on all three.")
    print(" 2. Note the 'Weekly Faculty v2' rubric id above; reuse it via rubric_association for D05+.")


if __name__ == "__main__":
    main()
