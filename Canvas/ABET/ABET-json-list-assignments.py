import json
from tabulate import tabulate

# Specify the path to your JSON file
input_file = 'response_data.json'

# Read the JSON data from the file
with open(input_file, 'r') as f:
    data = json.load(f)

assignments = data.get('course', {}).get('assignmentsConnection', {}).get('nodes', {})
#assignments = data

#print(json.dumps(assignments, indent=2))

for item in assignments:
    # Ensure '_id' and 'name' exist in the object
    _id = item.get('_id')
    name = item.get('name')
    
    print(f" ID: {_id}, Name: {name}")