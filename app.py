from flask import Flask, request, render_template, Response
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import requests
import json
import os
import re
import pandas as pd
import io
from flask_cors import CORS

app = Flask(__name__, template_folder="templates")
CORS(app, supports_credentials=True)

API_URL = "https://api-inference.huggingface.co/models/google/gemma-2-2b-it"
HEADERS = {"Authorization": "Bearer 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"}

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


@app.route('/')
def index():
    return render_template("index.html")  # ✅ Serves the upload page


def _read_file_from_path(path):
    """Reads text from a PDF file using pdfplumber. If empty, use OCR."""
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    if text.strip():
        return text.strip()

    print(f"⚠️ No text extracted from {path}, using OCR...")
    return _extract_text_using_ocr(path)


def _extract_text_using_ocr(pdf_path):
    """Applies OCR to extract text from an image-based PDF."""
    images = convert_from_path(pdf_path)
    extracted_text = ""

    for img in images:
        extracted_text += pytesseract.image_to_string(img) + "\n"

    return extracted_text.strip()


def query_huggingface(payload):
    """Sends resume text to Hugging Face API for structured extraction."""
    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error calling Hugging Face API: {e}")
        return None


def extract_resume_sections(pdf_text):
    prompt = '''
    You are an AI bot designed to act as a professional for parsing resumes. 
    Extract the following details **strictly in JSON format** without any extra text:
    1. full_name
    2. title
    3. email
    4. skills (avoid subheadings)
    '''
    input_text = f"Context: {pdf_text}\nInstruction: {prompt}\nAnswer:"
    payload = {
        "inputs": input_text,
        "parameters": {"max_new_tokens": 500}
    }
    output = query_huggingface(payload)
    if not output or not isinstance(output, list) or 'generated_text' not in output[0]:
        return {"error": "Invalid response from Hugging Face API"}

    response = output[0]['generated_text']

    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            json_data = json.loads(json_match.group())
            return json_data
        except json.JSONDecodeError:
            return {"error": "Failed to parse the response data"}
    return {"error": "No JSON data found in the response"}


@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    """Handles multiple file uploads and returns a downloadable CSV file."""
    if 'files' not in request.files:
        return {"error": "No files part"}, 400

    files = request.files.getlist('files')

    if not files or all(file.filename == '' for file in files):
        return {"error": "No selected files"}, 400

    extracted_data = []

    for file in files:
        try:
            pdf_path = f"uploaded_{file.filename}"
            file.save(pdf_path)

            text = _read_file_from_path(pdf_path)
            resume_data = extract_resume_sections(text)

            structured_output = {
                "file_name": file.filename,
                "full_name": resume_data.get("full_name", ""),
                "title": resume_data.get("title", ""),
                "email": resume_data.get("email", ""),
                "skills": "; ".join(resume_data.get("skills", []))
            }
            extracted_data.append(structured_output)

        except Exception as e:
            extracted_data.append({
                "file_name": file.filename,
                "error": f"Processing error: {str(e)}"
            })

    # ✅ Convert extracted data into CSV format
    df = pd.DataFrame(extracted_data)
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)

    # ✅ Return CSV file as a response to the frontend
    return Response(
        csv_buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=extracted_resumes.csv"}
    )


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Railway sets PORT dynamically
    app.run(debug=True, host="0.0.0.0", port=port)  # ✅ Must listen on 0.0.0.0
