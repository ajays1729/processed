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
        docx_path = convert_doc_to_docx(tmp_doc_path)
        if not docx_path or not os.path.exists(docx_path):
            print("Failed to convert .doc to .docx")
            return {"error": "Failed to convert .doc to .docx"}

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
        # Handle nested JSON structure
        if isinstance(candidate_data, str):
            # First JSON parse
            data = json.loads(candidate_data)
            # Check if it's a list with a json field
            if isinstance(data, list) and len(data) > 0 and "json" in data[0]:
                # Second JSON parse for the nested structure
                candidate_data = json.loads(data[0]["json"])
            else:
                candidate_data = data
        
        if not isinstance(candidate_data, dict):
            raise ValueError("Candidate data must be a dictionary after parsing.")

        # Remove trailing spaces from all keys and handle space after key name
        candidate_data = {key.strip(): value for key, value in candidate_data.items()}

        def extract_skills(skill_data):
            if not skill_data:
                return set()
            
            if isinstance(skill_data, list):
                # Join all items and split by commas to handle nested lists
                skills_text = ", ".join(str(item) for item in skill_data)
            else:
                skills_text = str(skill_data)
            
            # Split by commas and clean up each skill
            skills = set()
            for skill in skills_text.split(','):
                cleaned_skill = skill.strip()
                if cleaned_skill:
                    skills.add(cleaned_skill)
            return skills

        # Handle both variations of key names (with and without space)
        ideal_mandatory_skills = extract_skills(
            candidate_data.get("Ideal Mandatory Skills") or 
            candidate_data.get("Ideal Mandatory Skills ")
        )
        ideal_critical_skills = extract_skills(
            candidate_data.get("Ideal Critical Skills") or 
            candidate_data.get("Ideal Critical Skills ")
        )
        ideal_secondary_skills = extract_skills(
            candidate_data.get("Ideal Secondary Skills") or 
            candidate_data.get("Ideal Secondary Skills ")
        )

        mandatory_skills = extract_skills(
            candidate_data.get("Mandatory Skills") or 
            candidate_data.get("Mandatory Skills ")
        )
        critical_skills = extract_skills(
            candidate_data.get("Critical Skills") or 
            candidate_data.get("Critical Skills ")
        )
        secondary_skills = extract_skills(
            candidate_data.get("Secondary Skills") or 
            candidate_data.get("Secondary Skills ")
        )

        # Debug statements
        print(f"Ideal Mandatory Skills: {ideal_mandatory_skills}")
        print(f"Candidate Mandatory Skills: {mandatory_skills}")
        print(f"Ideal Critical Skills: {ideal_critical_skills}")
        print(f"Candidate Critical Skills: {critical_skills}")
        print(f"Ideal Secondary Skills: {ideal_secondary_skills}")
        print(f"Candidate Secondary Skills: {secondary_skills}")

        # Skill matching with case-insensitive comparison
        def case_insensitive_intersection(set1, set2):
            return {s1 for s1 in set1 if any(s1.lower() == s2.lower() for s2 in set2)}

        def case_insensitive_difference(set1, set2):
            return {s1 for s1 in set1 if not any(s1.lower() == s2.lower() for s2 in set2)}

        found_critical_skills = list(case_insensitive_intersection(critical_skills, ideal_critical_skills))
        missing_critical_skills = list(case_insensitive_difference(ideal_critical_skills, critical_skills))
        critical_match_count = len(found_critical_skills)

        found_mandatory_skills = list(case_insensitive_intersection(mandatory_skills, ideal_mandatory_skills))
        missing_mandatory_skills = list(case_insensitive_difference(ideal_mandatory_skills, mandatory_skills))
        mandatory_match_count = len(found_mandatory_skills)

        found_secondary_skills = list(case_insensitive_intersection(secondary_skills, ideal_secondary_skills))
        missing_secondary_skills = list(case_insensitive_difference(ideal_secondary_skills, secondary_skills))
        secondary_match_count = len(found_secondary_skills)

        # Salary alignment check with proper type conversion
        current_salary_high_range = float(candidate_data.get("Salary_High Range", 0))
        expected_salary = float(candidate_data.get("Expected Salary", 0))

        salary_alignment = "Not Available"
        if current_salary_high_range > 0 and expected_salary > 0:
            if expected_salary <= 100:  # Convert if salary is in lakhs
                expected_salary *= 100000
            if expected_salary <= current_salary_high_range:
                salary_alignment = "Aligned"
            else:
                current_salary_high_range += 300000  # Adjust for wiggle room
                if expected_salary <= current_salary_high_range:
                    salary_alignment = "Adjusted"
                else:
                    salary_alignment = "Not Aligned"

        # Years of experience alignment check with proper type conversion
        ideal_years_of_experience = float(candidate_data.get("Ideal Years of Experience", 0))
        years_of_experience = float(candidate_data.get("Years of Experience", 0))

        experience_alignment = "Not Available"
        if ideal_years_of_experience > 0 and years_of_experience > 0:
            if years_of_experience >= ideal_years_of_experience:
                experience_alignment = "Aligned"
            elif years_of_experience >= ideal_years_of_experience - 1:
                experience_alignment = "Adjusted"
            else:
                experience_alignment = "Not Aligned"

        # Availability alignment check with proper type conversion
        available_in_days = float(candidate_data.get("Available In Number of Days", -1))
        availability_alignment = "Not Available"
        if available_in_days >= 0:
            if 0 <= available_in_days <= 30:
                availability_alignment = "Aligned"
            else:
                availability_alignment = "Not Aligned"

        # Fit/Not Fit determination
        fit_status = "Fit"
        fit_reason = "Candidate meets all requirements"

        if critical_match_count < len(ideal_critical_skills):
            fit_status = "Not Fit"
            fit_reason = "Missing critical skills"
        elif len(ideal_mandatory_skills) > 5 and len(missing_mandatory_skills) > 2:
            fit_status = "Not Fit"
            fit_reason = "Too many missing mandatory skills (more than 2 missing from 5+ required)"
        elif len(ideal_mandatory_skills) <= 5 and len(missing_mandatory_skills) > 1:
            fit_status = "Not Fit"
            fit_reason = "Too many missing mandatory skills (more than 1 missing from 5 or fewer required)"
        elif salary_alignment not in ["Aligned", "Adjusted"]:
            fit_status = "Not Fit"
            fit_reason = "Salary expectations not aligned"
        elif experience_alignment not in ["Aligned", "Adjusted"]:
            fit_status = "Not Fit"
            fit_reason = "Experience level not aligned"
        elif availability_alignment != "Aligned":
            fit_status = "Not Fit"
            fit_reason = "Availability not aligned"

        return {
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
            "Fit Status": fit_status,
            "Fit Reason": fit_reason
        }

    except (ValueError, json.JSONDecodeError) as e:
        print(f"Error during candidate evaluation: {str(e)}")
        return {"Error": str(e)}

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
