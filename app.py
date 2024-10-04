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

        # Extract skills ensuring they are treated correctly as lists of strings
        def extract_skills(skill_data):
            if isinstance(skill_data, list):
                return set(skill.strip() for skill in skill_data if isinstance(skill, str))
            elif isinstance(skill_data, str):
                return set(filter(None, skill_data.split(', ')))
            return set()

        ideal_mandatory_skills = extract_skills(candidate_data.get("Ideal Mandatory Skills", ""))
        ideal_critical_skills = extract_skills(candidate_data.get("Ideal Critical Skills", ""))
        ideal_secondary_skills = extract_skills(candidate_data.get("Ideal Secondary Skills", ""))

        mandatory_skills = extract_skills(candidate_data.get("Mandatory Skills", ""))
        critical_skills = extract_skills(candidate_data.get("Critical Skills", ""))
        secondary_skills = extract_skills(candidate_data.get("Secondary Skills", ""))

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

        # Return the result as a dictionary
        result = {
            "Ideal Mandatory Skills": list(ideal_mandatory_skills),
            "Found Mandatory Skills": found_mandatory_skills,
            "Missing Mandatory Skills": missing_mandatory_skills,
            "Mandatory Match Percentage": mandatory_match_percentage,
            "Ideal Critical Skills": list(ideal_critical_skills),
            "Found Critical Skills": found_critical_skills,
            "Missing Critical Skills": missing_critical_skills,
            "Critical Match Percentage": critical_match_percentage,
            "Ideal Secondary Skills": list(ideal_secondary_skills),
            "Found Secondary Skills": found_secondary_skills,
            "Missing Secondary Skills": missing_secondary_skills,
            "Secondary Match Percentage": secondary_match_percentage
        }

        return result

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
        candidate_data_str = request.form['candidate_data']
        try:
            # Load the JSON string inside the candidate_data
            candidate_data = json.loads(candidate_data_str)
            candidate_result = evaluate_candidate(candidate_data)
        except Exception as e:
            candidate_result["candidate_error"] = f"Error processing candidate data: {str(e)}"

    if not parsing_result and not candidate_result:
        return jsonify({"error": "No file or candidate data provided"}), 400

    return jsonify({"parsing_result": parsing_result, "candidate_result": candidate_result})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
