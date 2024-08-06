import os
from flask import Flask, request, jsonify
from pdfminer.high_level import extract_text
from docx import Document
import io

app = Flask(__name__)

def parse_pdf(file_stream):
    file_stream.seek(0)  # Ensure we're at the start of the file
    text = extract_text(file_stream)
    return {"type": "pdf", "content": text}

def parse_docx(file_stream):
    text = ""
    doc = Document(io.BytesIO(file_stream))
    for para in doc.paragraphs:
        text += para.text + "\n"
    return {"type": "docx", "content": text}

@app.route('/parse', methods=['POST'])
def parse_document():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    file_buffer = file.read()
    
    try:
        # Attempt to parse as PDF
        return jsonify(parse_pdf(io.BytesIO(file_buffer)))
    except Exception as e:
        # If PDF parsing fails, try DOCX parsing
        try:
            return jsonify(parse_docx(file_buffer))
        except Exception as e:
            return jsonify({"error": "Unsupported file type"}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
