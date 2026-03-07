import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
API_URL = os.getenv("API_URL")
COURSE_ID = os.getenv("COURSE_ID")

# Basic checks to ensure everything is loaded
if not ACCESS_TOKEN:
    raise ValueError("Missing ACCESS_TOKEN! Check your .env file.")
if not API_URL:
    raise ValueError("Missing API_URL! Check your .env file.")
if not COURSE_ID:
    raise ValueError("Missing COURSE_ID! Check your .env file.")

query_template = """
{
  course(id: {course_id}) {
    id
    name
    assignmentsConnection {
      nodes {
        name
        _id
        submissionsConnection {
          nodes {
            grade
            user {
              email
            }
            rubricAssessmentsConnection {
              nodes {
                assessmentRatings {
                  comments
                  description
                  points
                  criterion {
                    longDescription
                    points
                    description
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

query = query_template.format(course_id=COURSE_ID)

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# Make the request
response = requests.post(API_URL, json={'query': query}, headers=headers)

# Raise an exception for bad responses
response.raise_for_status()
data = response.json()

# Dump the response JSON to a file
output_file = 'response_data_unpaged.json'

with open(output_file, 'w') as f:
    json.dump(data, f, indent=2)

#Canvas paged this we need to fix that.