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
    file_stream.seek(0)
    text = extract_text(file_stream)
    return {"type": "pdf", "content": text}

def parse_docx(file_stream):
    text = ""
    doc = Document(file_stream)
    for para in doc.paragraphs:
        text += para.text + "\n"
    return {"type": "docx", "content": text}

def convert_doc_to_docx(doc_path):
    try:
        subprocess.run(['libreoffice', '--convert-to', 'docx', doc_path, '--headless'], check=True)
        return doc_path.replace('.doc', '.docx')
    except subprocess.CalledProcessError as e:
        return None

def parse_doc(file_stream):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.doc') as tmp_file:
        tmp_file.write(file_stream.read())
        tmp_doc_path = tmp_file.name

    try:
        # Convert .doc to .docx using LibreOffice
        docx_path = convert_doc_to_docx(tmp_doc_path)
        if not docx_path or not os.path.exists(docx_path):
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
        # Ensure the types of incoming data are as expected
        if isinstance(candidate_data, str):
            candidate_data = json.loads(candidate_data)
        if not isinstance(candidate_data, dict):
            raise ValueError("Candidate data must be a dictionary.")

        # Remove trailing spaces from all keys in the candidate data
        candidate_data = {key.strip(): value for key, value in candidate_data.items()}

        # Compare skills for each type separately
        ideal_mandatory_skills = set(str(candidate_data.get("Ideal Mandatory Skills", "")).split(', '))
        ideal_critical_skills = set(str(candidate_data.get("Ideal Critical Skills", "")).split(', '))
        ideal_secondary_skills = set(str(candidate_data.get("Ideal Secondary Skills", "")).split(', '))

        mandatory_skills = set(str(candidate_data.get("Mandatory Skills", "")).split(', '))
        critical_skills = set(str(candidate_data.get("Critical Skills", "")).split(', '))
        secondary_skills = set(str(candidate_data.get("Secondary Skills", "")).split(', '))

        if not all(isinstance(skill, str) for skill in mandatory_skills.union(critical_skills, secondary_skills)):
            raise ValueError("Skills must be provided as strings.")

        # Mandatory skills match
        found_mandatory_skills = list(mandatory_skills.intersection(ideal_mandatory_skills))
        missing_mandatory_skills = list(ideal_mandatory_skills - mandatory_skills)
        mandatory_match_percentage = (len(found_mandatory_skills) / len(ideal_mandatory_skills)) * 100 if ideal_mandatory_skills else 0

        # Critical skills match
        found_critical_skills = list(critical_skills.intersection(ideal_critical_skills))
        missing_critical_skills = list(ideal_critical_skills - critical_skills)
        critical_match_percentage = (len(found_critical_skills) / len(ideal_critical_skills)) * 100 if ideal_critical_skills else 0

        # Secondary skills match
        found_secondary_skills = list(secondary_skills.intersection(ideal_secondary_skills))
        missing_secondary_skills = list(ideal_secondary_skills - secondary_skills)
        secondary_match_percentage = (len(found_secondary_skills) / len(ideal_secondary_skills)) * 100 if ideal_secondary_skills else 0

        # Salary alignment check
        current_salary_high_range = candidate_data.get("Salary_High Range", None)
        expected_salary = candidate_data.get("Expected Salary", None)

        if not isinstance(current_salary_high_range, (int, float)) or not isinstance(expected_salary, (int, float)):
            raise ValueError("Salary information must be numeric.")

        if expected_salary <= 100:
            expected_salary *= 100000

        if expected_salary <= current_salary_high_range:
            salary_alignment = "Aligned"
        else:
            current_salary_high_range += 300000
            if expected_salary == current_salary_high_range:
                salary_alignment = "Adjusted"
            else:
                salary_alignment = "Not Aligned"
                negotiable_salary = expected_salary * 0.3 + expected_salary
                if negotiable_salary <= current_salary_high_range:
                    salary_alignment = "Negotiable"

        # Years of experience alignment check
        ideal_years_of_experience = candidate_data.get("Ideal Years of Experience", None)
        years_of_experience = candidate_data.get("Years of Experience", None)

        if not isinstance(ideal_years_of_experience, int) or not isinstance(years_of_experience, int):
            raise ValueError("Years of experience must be integers.")

        if years_of_experience >= ideal_years_of_experience:
            experience_alignment = "Aligned"
        elif years_of_experience == ideal_years_of_experience - 1:
            experience_alignment = "Adjusted"
        else:
            experience_alignment = "Not Aligned"

        # Availability alignment check
        available_in_days = candidate_data.get("Available In Number of Days", None)

        if not isinstance(available_in_days, int):
            raise ValueError("Availability information must be an integer.")

        if 0 <= available_in_days <= 30:
            availability_alignment = "Aligned"
        else:
            availability_alignment = "Not Aligned"

        # Fit/Not Fit determination
        fit_status = "Fit"
        if critical_match_percentage < 100:
            fit_status = "Not Fit"
        elif mandatory_match_percentage < 85:
            fit_status = "Not Fit"
        elif salary_alignment not in ["Aligned", "Adjusted", "Negotiable"]:
            fit_status = "Not Fit"
        elif experience_alignment not in ["Aligned", "Adjusted"]:
            fit_status = "Not Fit"
        elif availability_alignment not in ["Aligned", "Adjusted"]:
            fit_status = "Not Fit"

        # Ensure fit status is included in the output
        result = {
            "Found Mandatory Skills": found_mandatory_skills,
            "Missing Mandatory Skills": missing_mandatory_skills,
            "Mandatory Match Percentage": mandatory_match_percentage,
            "Found Critical Skills": found_critical_skills,
            "Missing Critical Skills": missing_critical_skills,
            "Critical Match Percentage": critical_match_percentage,
            "Found Secondary Skills": found_secondary_skills,
            "Missing Secondary Skills": missing_secondary_skills,
            "Secondary Match Percentage": secondary_match_percentage,
            "Salary Alignment": salary_alignment,
            "Experience Alignment": experience_alignment,
            "Availability Alignment": availability_alignment,
            "Fit Status": fit_status
        }

        return result

    except KeyError as e:
        return {"Error": f"Missing key in candidate data: {str(e)}"}
    except ValueError as e:
        return {"Error": str(e)}
    except json.JSONDecodeError as e:
        return {"Error": f"Invalid JSON format: {str(e)}"}

@app.route('/parse', methods=['POST'])
def parse_document():
    response_data = {}
    parsing_result = {}
    candidate_result = {}

    if 'file' in request.files:
        file = request.files['file']
        if not file.filename:
            parsing_result["file_error"] = "No file selected"
        else:
            file_buffer = file.read()
            file_extension = os.path.splitext(file.filename)[1].lower()

            if not file_extension:
                parsing_result["file_error"] = "File has no extension"
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
                except Exception as e:
                    parsing_result["file_error"] = f"Error processing file: {str(e)}"

    if 'candidate_data' in request.form:
        candidate_data = request.form['candidate_data']
        try:
            candidate_result = evaluate_candidate(candidate_data)
        except Exception as e:
            candidate_result["candidate_error"] = f"Error processing candidate data: {str(e)}"

    if not parsing_result and not candidate_result:
        return jsonify({"error": "No file or candidate data provided"}), 400

    return jsonify({"parsing_result": parsing_result, "candidate_result": candidate_result})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
