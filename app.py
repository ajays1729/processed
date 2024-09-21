import os
from flask import Flask, request, jsonify
from pdfminer.high_level import extract_text
from docx import Document
import io
import subprocess
import tempfile

app = Flask(__name__)

def parse_pdf(file_stream):
    file_stream.seek(0)  # Ensure we're at the start of the file
    text = extract_text(file_stream)
    return {"type": "pdf", "content": text}

def parse_docx(file_stream):
    text = ""
    doc = Document(file_stream)
    for para in doc.paragraphs:
        text += para.text + "\n"
    return {"type": "docx", "content": text}

def parse_doc(file_stream):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.doc') as tmp_file:
        tmp_file.write(file_stream.read())
        tmp_file_path = tmp_file.name

    try:
        # Use antiword to extract text from the .doc file
        result = subprocess.run(
            ['antiword', tmp_file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        text = result.stdout.decode('utf-8')
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8')
        return {"error": f"Failed to parse .doc file: {error_msg}"}
    finally:
        os.unlink(tmp_file_path)  # Clean up the temporary file

    return {"type": "doc", "content": text}

@app.route('/parse', methods=['POST'])
def parse_document():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    file_buffer = file.read()
    file_extension = os.path.splitext(file.filename)[1].lower()

    if not file_extension:
        return jsonify({"error": "File has no extension"}), 400

    try:
        file_stream = io.BytesIO(file_buffer)
        if file_extension == '.pdf':
            return jsonify(parse_pdf(file_stream))
        elif file_extension == '.docx':
            return jsonify(parse_docx(file_stream))
        elif file_extension == '.doc':
            return jsonify(parse_doc(file_stream))
        else:
            return jsonify({"error": "Unsupported file type"}), 400
    except Exception as e:
        return jsonify({"error": f"Error processing file: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
