from flask import Flask, request, jsonify
import fitz  # PyMuPDF
from docx import Document
import io

app = Flask(__name__)

def parse_pdf(file_stream):
    text = ""
    pdf_document = fitz.open(stream=file_stream, filetype="pdf")
    for page_num in range(pdf_document.page_count):
        page = pdf_document.load_page(page_num)
        text += page.get_text()
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
        return jsonify(parse_pdf(file_buffer))
    except Exception as e:
        # If PDF parsing fails, try DOCX parsing
        try:
            return jsonify(parse_docx(file_buffer))
        except Exception as e:
            return jsonify({"error": "Unsupported file type"}), 400

if __name__ == '__main__':
    app.run(debug=True)
