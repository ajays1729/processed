import os
import json
from flask import Flask, request, jsonify
from pdfminer.high_level import extract_text
from docx import Document
import io
import subprocess
import tempfile

app = Flask(__name__)

def parse_pdf(file_stream):
    print("Starting PDF parsing...")
    file_stream.seek(0)
    text = extract_text(file_stream)
    print(f"PDF parsing completed. Extracted text length: {len(text)}")
    return {"type": "pdf", "content": text}

def parse_docx(file_stream):
    print("Starting DOCX parsing...")
    text = ""
    doc = Document(file_stream)
    for para in doc.paragraphs:
        text += para.text + "\n"
    print(f"DOCX parsing completed. Extracted text length: {len(text)}")
    return {"type": "docx", "content": text}

def convert_doc_to_docx(doc_path):
    print(f"Converting .doc to .docx: {doc_path}")
    try:
        subprocess.run(['libreoffice', '--convert-to', 'docx', doc_path, '--headless'], check=True)
        converted_path = doc_path.replace('.doc', '.docx')
        print(f"Conversion successful: {converted_path}")
        return converted_path
    except subprocess.CalledProcessError as e:
        print(f"Conversion failed: {e}")
        return None

def parse_doc(file_stream):
    print("Starting DOC parsing...")
    with tempfile.NamedTemporaryFile(delete=False, suffix='.doc') as tmp_file:
        tmp_file.write(file_stream.read())
        tmp_doc_path = tmp_file.name

    try:
        # Convert .doc to .docx using LibreOffice
        docx_path = convert_doc_to_docx(tmp_doc_path)
        if not docx_path or not os.path.exists(docx_path):
            print("Failed to convert .doc to .docx")
            return {"error": "Failed to convert .doc to .docx"}

        # Parse the converted .docx file
        with open(docx_path, 'rb') as docx_file:
            return parse_docx(docx_file)
    finally:
        if os.path.exists(tmp_doc_path):
            os.unlink(tmp_doc_path)
        if docx_path and os.path.exists(docx_path):
            os.unlink(docx_path)

def evaluate_candidate(candidate_data):
    try:
        print("Starting candidate evaluation...")
        # Ensure the types of incoming data are as expected
        if isinstance(candidate_data, str):
            candidate_data = json.loads(candidate_data)
        if not isinstance(candidate_data, dict):
            raise ValueError("Candidate data must be a dictionary.")

        # Remove trailing spaces from all keys in the candidate data
        candidate_data = {key.strip(): value for key, value in candidate_data.items()}

        # Extract skills ensuring they are treated correctly as lists of strings
        def extract_skills(skill_data):
            if isinstance(skill_data, list):
                skills = set()
                for item in skill_data:
                    if isinstance(item, str):
                        # Split skills by comma and strip whitespace
                        skills.update(skill.strip() for skill in item.split(',') if skill.strip())
                return skills
            elif isinstance(skill_data, str):
                # Split skills by comma and strip whitespace
                return set(skill.strip() for skill in skill_data.split(',') if skill.strip())
            return set()

        ideal_mandatory_skills = extract_skills(candidate_data.get("Ideal Mandatory Skills", ""))
        ideal_critical_skills = extract_skills(candidate_data.get("Ideal Critical Skills", ""))
        ideal_secondary_skills = extract_skills(candidate_data.get("Ideal Secondary Skills", ""))

        mandatory_skills = extract_skills(candidate_data.get("Mandatory Skills", ""))
        critical_skills = extract_skills(candidate_data.get("Critical Skills", ""))
        secondary_skills = extract_skills(candidate_data.get("Secondary Skills", ""))

        # Debug statements to print extracted skills
        print(f"Ideal Mandatory Skills: {ideal_mandatory_skills}")
        print(f"Candidate Mandatory Skills: {mandatory_skills}")
        print(f"Ideal Critical Skills: {ideal_critical_skills}")
        print(f"Candidate Critical Skills: {critical_skills}")
        print(f"Ideal Secondary Skills: {ideal_secondary_skills}")
        print(f"Candidate Secondary Skills: {secondary_skills}")

        if not all(isinstance(skill, str) for skill in mandatory_skills.union(critical_skills, secondary_skills)):
            raise ValueError("Skills must be provided as strings.")

        # Critical skills match
        found_critical_skills = list(critical_skills.intersection(ideal_critical_skills))
        missing_critical_skills = list(ideal_critical_skills - critical_skills)
        critical_match_count = len(found_critical_skills)
        print(f"Critical skills match: {critical_match_count}/{len(ideal_critical_skills)}")

        # If not all critical skills are matched, candidate is not fit
        if critical_match_count < len(ideal_critical_skills):
            fit_status = "Not Fit"
            print(f"Final fit status: {fit_status} due to missing critical skills")
            return {"Fit Status": fit_status}

        # Mandatory skills match
        found_mandatory_skills = list(mandatory_skills.intersection(ideal_mandatory_skills))
        missing_mandatory_skills = list(ideal_mandatory_skills - mandatory_skills)
        mandatory_match_count = len(found_mandatory_skills)
        print(f"Mandatory skills match: {mandatory_match_count}/{len(ideal_mandatory_skills)}")

        # Allow up to 2 missing mandatory skills if ideal mandatory skills are more than 5
        # Allow up to 1 missing mandatory skill if ideal mandatory skills are 5 or less
        if len(ideal_mandatory_skills) > 5 and len(missing_mandatory_skills) > 2:
            fit_status = "Not Fit"
            print(f"Final fit status: {fit_status} due to too many missing mandatory skills")
            return {"Fit Status": fit_status}
        elif len(ideal_mandatory_skills) <= 5 and len(missing_mandatory_skills) > 1:
            fit_status = "Not Fit"
            print(f"Final fit status: {fit_status} due to too many missing mandatory skills")
            return {"Fit Status": fit_status}

        # Secondary skills match
        found_secondary_skills = list(secondary_skills.intersection(ideal_secondary_skills))
        missing_secondary_skills = list(ideal_secondary_skills - secondary_skills)
        secondary_match_count = len(found_secondary_skills)
        print(f"Secondary skills match: {secondary_match_count}/{len(ideal_secondary_skills)}")

        # Salary alignment check
        current_salary_high_range = candidate_data.get("Salary_High Range")
        expected_salary = candidate_data.get("Expected Salary")

        salary_alignment = "Not Available"
        if current_salary_high_range is not None and expected_salary is not None:
            if expected_salary <= 100:
                expected_salary *= 100000
            if expected_salary <= current_salary_high_range:
                salary_alignment = "Aligned"
            else:
                current_salary_high_range += 300000  # Adjust for wiggle room
                if expected_salary <= current_salary_high_range:
                    salary_alignment = "Adjusted"
                else:
                    salary_alignment = "Not Aligned"
        print(f"Salary alignment: {salary_alignment}")

        # Years of experience alignment check
        ideal_years_of_experience = candidate_data.get("Ideal Years of Experience")
        years_of_experience = candidate_data.get("Years of Experience")

        experience_alignment = "Not Available"
        if ideal_years_of_experience is not None and years_of_experience is not None:
            if years_of_experience >= ideal_years_of_experience:
                experience_alignment = "Aligned"
            elif years_of_experience >= ideal_years_of_experience - 1:
                experience_alignment = "Adjusted"
            else:
                experience_alignment = "Not Aligned"
        print(f"Years of experience alignment: {experience_alignment}")

        # Availability alignment check
        available_in_days = candidate_data.get("Available In Number of Days")

        availability_alignment = "Not Available"
        if available_in_days is not None:
            if 0 <= available_in_days <= 30:
                availability_alignment = "Aligned"
            else:
                availability_alignment = "Not Aligned"
        print(f"Availability alignment: {availability_alignment}")

        # Fit/Not Fit determination
        fit_status = "Fit"
        if salary_alignment != "Aligned" and salary_alignment != "Adjusted":
            fit_status = "Not Fit"
        elif experience_alignment != "Aligned" and experience_alignment != "Adjusted":
            fit_status = "Not Fit"
        elif availability_alignment != "Aligned":
            fit_status = "Not Fit"
        print(f"Final fit status: {fit_status}")

        # Return the result as a dictionary
        result = {
            "Ideal Mandatory Skills": list(ideal_mandatory_skills),
            "Found Mandatory Skills": found_mandatory_skills,
            "Missing Mandatory Skills": missing_mandatory_skills,
            "Mandatory Match": f"{mandatory_match_count}/{len(ideal_mandatory_skills)}",
            "Ideal Critical Skills": list(ideal_critical_skills),
            "Found Critical Skills": found_critical_skills,
            "Missing Critical Skills": missing_critical_skills,
            "Critical Match": f"{critical_match_count}/{len(ideal_critical_skills)}",
            "Ideal Secondary Skills": list(ideal_secondary_skills),
            "Found Secondary Skills": found_secondary_skills,
            "Missing Secondary Skills": missing_secondary_skills,
            "Secondary Match": f"{secondary_match_count}/{len(ideal_secondary_skills)}",
            "Salary Alignment": salary_alignment,
            "Experience Alignment": experience_alignment,
            "Availability Alignment": availability_alignment,
            "Fit Status": fit_status
        }

        print("Candidate evaluation completed.")
        return result

    except ValueError as e:
        print(f"ValueError during candidate evaluation: {e}")
        return {"Error": str(e)}
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError during candidate evaluation: {e}")
        return {"Error": f"Invalid JSON format: {str(e)}"}

@app.route('/parse', methods=['POST'])
def parse_document():
    print("Received request to /parse endpoint")
    response_data = {}
    parsing_result = {}
    candidate_result = {}

    if 'file' in request.files:
        file = request.files['file']
        if not file.filename:
            parsing_result["file_error"] = "No file selected"
            print("No file selected for parsing")
        else:
            file_buffer = file.read()
            file_extension = os.path.splitext(file.filename)[1].lower()
            print(f"File received: {file.filename}, Extension: {file_extension}")

            if not file_extension:
                parsing_result["file_error"] = "File has no extension"
                print("File has no extension")
            else:
                try:
                    file_stream = io.BytesIO(file_buffer)
                    if file_extension == '.pdf':
                        parsing_result = parse_pdf(file_stream)
                    elif file_extension == '.docx':
                        parsing_result = parse_docx(file_stream)
                    elif file_extension == '.doc':
                        parsing_result = parse_doc(file_stream)
                    else:
                        parsing_result["file_error"] = "Unsupported file type"
                        print("Unsupported file type")
                except Exception as e:
                    parsing_result["file_error"] = f"Error processing file: {str(e)}"
                    print(f"Error processing file: {e}")

    if 'candidate_data' in request.form:
        candidate_data = request.form['candidate_data']
        try:
            candidate_result = evaluate_candidate(candidate_data)
        except Exception as e:
            candidate_result = {"error": f"Error evaluating candidate: {str(e)}"}
            print(f"Error evaluating candidate: {e}")

    response_data["parsing_result"] = parsing_result
    response_data["candidate_result"] = candidate_result

    return jsonify(response_data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
