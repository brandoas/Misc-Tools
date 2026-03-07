import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
API_URL = os.getenv("API_URL")

# Basic checks to ensure everything is loaded
if not ACCESS_TOKEN:
    raise ValueError("Missing ACCESS_TOKEN! Check your .env file.")
if not API_URL:
    raise ValueError("Missing API_URL! Check your .env file.")

#Prompt for class number to select below
try:
    COURSE_ID = input("Enter the Canvas course number to query data for: ").strip()
except ValueError:
    print("Invalid input. Please enter a numeric class number.")
    exit(1)
        
headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# Define the query with pagination for assignmentsConnection
# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Path to the .graphql file relative to the script
query_file_path = os.path.join(script_dir, "rubric-results-paged.graphql")

print (query_file_path)

# Load and substitute the course ID into the query
with open(query_file_path, 'r') as f:
    raw_query = f.read()

print (raw_query)

query = raw_query.replace("COURSE_ID", COURSE_ID)

print(query)

def fetch_all_data():
    # Use a dictionary to store the data directly under 'course' instead of an array
    all_data = {}

    # Initial request to get the first page of course data with assignmentsConnection
    variables = {}
    query_data = {"query": query}
    
    while True:
        response = requests.post(API_URL, json=query_data, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Update the 'course' data in the dictionary
        course_data = data.get('data', {}).get('course', {})
        all_data['course'] = course_data

        # Extract the assignments and submissions data from the response
        assignments = course_data.get('assignmentsConnection', {}).get('nodes', [])
        
        # Check if there are more pages for assignments
        page_info = course_data.get('assignmentsConnection', {}).get('pageInfo', {})
        if not page_info.get('hasNextPage'):
            break
        
        # If there's a next page, modify the query to include the `endCursor`
        end_cursor = page_info.get('endCursor')
        query_data["query"] = query.replace("first: 100", f"first: 100, after: \"{end_cursor}\"")

    return all_data

# Fetch all the data
all_course_data = fetch_all_data()

# Dump the response JSON to a file
output_file = 'response_data.json'
with open(output_file, 'w') as f:
    json.dump(all_course_data, f, indent=2)

print(f"Data has been fetched and saved to {output_file}")
