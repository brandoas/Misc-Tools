import json
from tabulate import tabulate
import argparse

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Process Canvas assignment data")
parser.add_argument("-f", "--file", default="response_data.json", help="Path to the input JSON file")
group = parser.add_mutually_exclusive_group()
group.add_argument("-s", "--filter_students", action="store_true", help="List of student emails to include")
group.add_argument("-S", "--one_filter_students", action="store_true", help="Single student email to include")
args = parser.parse_args()

input_file = args.file
filter_students = args.filter_students
one_filter_students = args.one_filter_students

# Read the JSON data from the file
with open(input_file, 'r') as f:
    data = json.load(f)

assignments = data.get('course', {}).get('assignmentsConnection', {}).get('nodes', {})
table_data = []
student_filter = []

if one_filter_students:
    try:
        student_filter = input("Enter a comma seperated list of email addresses to filter for every class: ").strip().split(",")
        for i in range(len(student_filter)):
            student_filter[i] = student_filter[i].strip()
        filter_students = True
    except ValueError:
        print("Invalid input. Please enter a numeric class number.")
        exit(1)

#Going to list the assignments
for item in assignments:
    # Ensure '_id' and 'name' exist in the object
    _id = item.get('_id')
    name = item.get('name')
    
    print(f" ID: {_id}, Name: {name}")

#Prompt for assignment number to select below
try:
    assign_num = int(input("Enter an assignment number [0 for all]: ").strip())
except ValueError:
    print("Invalid input. Please enter a numeric class number.")
    exit(1)


#Looping through assignments
for item in assignments:
    # Ensure '_id' and 'name' exist in the object

    _id = item.get('_id')
    name = item.get('name')

    #Find the assignment that was selected
    if int(_id) == assign_num or int(assign_num) == 0:

        #Get the student filter for this assignment
        if filter_students and not one_filter_students:
            try:
                print(f" ID: {_id}, Name: {name}")
                student_filter = input("Enter a comma seperated list of email addresses to filter for this class: ").strip().split(",")
                for i in range(len(student_filter)):
                    student_filter[i] = student_filter[i].strip()

            except ValueError:
                print("Invalid input. Please enter a list of students.")
                exit(1)

        #Open the file and gather the rest of the data
        with open(f"{name}-{_id}-feedback.txt", "w", encoding="utf-8") as output_file:
            #Print the Assigment that was selected      
            output_file.write(f" ID: {_id}, Name: {name}\n") 

            #Select the respective assignments and loop over them.
            submissions = item.get('submissionsConnection', {}).get('nodes', {})
            for submission in submissions:
                student = submission.get('user').get('email')

                if not filter_students or student in student_filter:   
                    print(f"Student: {student}")
                    output_file.write("\n\n")
                    # Print the Students Email address

                    output_file.write(f"Student: {student}\n")

                    # If they have a grade
                    grade = submission.get('grade')
                    if grade is not None:
                        output_file.write(f"Grade: {grade}\n")
                    else:
                        output_file.write("Student did not receive a grade\n")

                    #Print the Rubric 
                    rubric_conn = submission.get('rubricAssessmentsConnection', {})
                    rubric_items = rubric_conn.get('nodes', [])
                    if rubric_items:
                        table_data = []
                        for rubric_item in rubric_items:
                            if 'assessmentRatings' in rubric_item:

                                for assessment in rubric_item.get('assessmentRatings', {}):
                                    criterion_desc = assessment['criterion']['description']
                                    points = assessment['points']
                                    comments = assessment['comments']
                                    table_data.append([criterion_desc, points, comments])
                        
                                if table_data is not None:
                                    # Define the table headers
                                    headers = ["Criterion", "Points", "Comments"]

                                    # Print the table
                                    output_file.write("Grading Rubric:\n")
                                    output_file.write(tabulate(table_data, headers=headers, tablefmt="grid"))
                                    output_file.write("\n")

                    #Print the General Feedback.
                    comments_items = submission.get('commentsConnection', {}).get('nodes', {})
                    if comments_items:
                        table_data = []
                        for comments_item in comments_items:  
                            if 'comment' in comments_item:

                                comment_text = comments_item['comment']
                                author = comments_item['author']['email']
                                table_data.append([author, comment_text])

                            if table_data is not None:
                                # Define the table headers
                                headers = ["Author","Comment"]

                                # Print the table
                                output_file.write("General Comments:\n")
                                output_file.write(tabulate(table_data, headers=headers, tablefmt="grid"))
                                output_file.write("\n")

#       print(json.dumps(rubrics_items, indent=2))