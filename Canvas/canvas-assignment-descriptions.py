import requests
import json
import os
import re
from dotenv import load_dotenv

# Load environment variables - looks for .env in this directory first
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# Support both API_URL and CANVAS_URL (the .env uses CANVAS_URL)
API_URL = os.getenv("API_URL") or os.getenv("CANVAS_URL", "").split("#")[0].strip()

# Course ID: use .env value or prompt at runtime
COURSE_ID = os.getenv("COURSE_ID")
if not COURSE_ID:
    try:
        COURSE_ID = input("Enter the Canvas course ID to query: ").strip()
    except (ValueError, EOFError):
        print("Invalid input.")
        exit(1)

# Basic checks
if not ACCESS_TOKEN:
    raise ValueError("Missing ACCESS_TOKEN - check your .env file.")
if not API_URL:
    raise ValueError("Missing API_URL or CANVAS_URL - check your .env file.")
if not COURSE_ID:
    raise ValueError("No course ID provided.")

print(f"Querying course {COURSE_ID} at {API_URL}")

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# GraphQL query - fetches assignments with full descriptions, points, groups, and due dates.
# Uses cursor-based pagination (first: 50 per page) to handle large courses.
QUERY_TEMPLATE = """
{{
  course(id: "{course_id}") {{
    id
    _id
    name
    assignmentsConnection(first: 50{after}) {{
      pageInfo {{
        hasNextPage
        endCursor
      }}
      nodes {{
        _id
        name
        description
        pointsPossible
        dueAt
        submissionTypes
        position
        assignmentGroup {{
          name
        }}
      }}
    }}
  }}
}}
"""


def strip_html(html):
    """Strip HTML tags and normalize whitespace for readable plain-text output."""
    if not html:
        return ""
    # Replace common block elements with newlines
    text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '  - ', text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode common HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def fetch_all_assignments(course_id):
    """Fetch all assignment pages and return a flat list of nodes."""
    all_assignments = []
    course_name = None
    cursor = None

    while True:
        after_clause = f', after: "{cursor}"' if cursor else ""
        query = QUERY_TEMPLATE.format(course_id=course_id, after=after_clause)

        response = requests.post(API_URL, json={"query": query}, headers=headers)
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            print("GraphQL errors:")
            for err in data["errors"]:
                print(" ", err.get("message"))
            break

        course_data = data.get("data", {}).get("course", {})
        if not course_data:
            print("No course data returned. Check that the course ID is correct and your token has access.")
            break

        if course_name is None:
            course_name = course_data.get("name", "Unknown Course")

        conn = course_data.get("assignmentsConnection", {})
        nodes = conn.get("nodes", [])
        all_assignments.extend(nodes)

        page_info = conn.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break

        cursor = page_info.get("endCursor")
        print(f"  Fetched {len(all_assignments)} assignments so far, loading next page...")

    return course_name, all_assignments


# --- Run the query ---
course_name, assignments = fetch_all_assignments(COURSE_ID)
print(f"\nCourse: {course_name}")
print(f"Total assignments found: {len(assignments)}")

# Sort by assignment group name, then position within group
assignments.sort(key=lambda a: (
    a.get("assignmentGroup", {}).get("name") or "zzz",
    a.get("position") or 9999
))

# --- Save raw JSON ---
raw_output_file = f"assignments_{COURSE_ID}_raw.json"
with open(raw_output_file, "w") as f:
    json.dump({"course": course_name, "assignments": assignments}, f, indent=2)
print(f"Raw JSON saved to: {raw_output_file}")

# --- Save human-readable text summary ---
text_output_file = f"assignments_{COURSE_ID}_descriptions.txt"
with open(text_output_file, "w", encoding="utf-8") as f:
    f.write(f"Assignment Descriptions\n")
    f.write(f"Course: {course_name} (ID: {COURSE_ID})\n")
    f.write("=" * 80 + "\n\n")

    current_group = None
    for a in assignments:
        group = (a.get("assignmentGroup") or {}).get("name", "Ungrouped")
        if group != current_group:
            current_group = group
            f.write(f"\n{'=' * 80}\n")
            f.write(f"GROUP: {group}\n")
            f.write(f"{'=' * 80}\n\n")

        name = a.get("name", "Untitled")
        pts = a.get("pointsPossible")
        due = a.get("dueAt") or "No due date"
        sub_types = ", ".join(a.get("submissionTypes") or [])
        description_raw = a.get("description") or ""
        description_clean = strip_html(description_raw)

        f.write(f"Assignment: {name}\n")
        f.write(f"  ID:          {a.get('_id')}\n")
        f.write(f"  Points:      {pts}\n")
        f.write(f"  Due:         {due}\n")
        f.write(f"  Submission:  {sub_types}\n")
        f.write(f"  Description:\n")
        if description_clean:
            for line in description_clean.splitlines():
                f.write(f"    {line}\n")
        else:
            f.write("    (no description)\n")
        f.write("\n" + "-" * 60 + "\n\n")

print(f"Readable summary saved to: {text_output_file}")

# --- Print a quick console summary ---
print("\nAssignment list:")
current_group = None
for a in assignments:
    group = (a.get("assignmentGroup") or {}).get("name", "Ungrouped")
    if group != current_group:
        current_group = group
        print(f"\n  [{group}]")
    pts = a.get("pointsPossible")
    print(f"    {a.get('name')}  ({pts} pts)")
