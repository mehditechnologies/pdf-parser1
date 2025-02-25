from flask import Flask, request, jsonify, render_template
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import requests
import json
import os
import re
import pandas as pd
from flask_cors import CORS

app = Flask(__name__, template_folder="templates")
CORS(app, supports_credentials=True)

JSON_FILE = "resume_data.json"
CSV_FILE = "resume_data.csv"
API_URL = "https://api-inference.huggingface.co/models/google/gemma-2-2b-it"
HEADERS = {"Authorization": "Bearer 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"}

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DEBUG_MODE = True  # Set to False to disable extra logging
MAX_LENGTH = 3000  # Limit text size to prevent API truncation


@app.route('/')
def index():
    return render_template("index.html")


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
        response_text = response.json()
        return response_text
    except requests.exceptions.RequestException as e:
        print(f"❌ Error calling Hugging Face API: {e}")
        return None


def extract_json_from_response(response_text):
    """Extracts JSON data safely from API response, even if extra text exists."""
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())  # Parse JSON
        except json.JSONDecodeError:
            return {"error": "Invalid JSON format"}
    return {"error": "No JSON data found"}


def extract_resume_sections(pdf_text):
    prompt = '''
    You are an AI bot designed to act as a professional for parsing resumes. You are given a resume data, and your job is to extract the following information & Return the extracted information **strictly in JSON format only** without any extra text.Return ONLY a JSON object between triple backticks. Use "HTML/CSS" instead of "HTML\\CSS"
    1. full_name
    2. title
    3. email
    4. skills (skills only avoid subheadings)
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


def save_to_json(data):
    """Saves extracted resume data into JSON file."""
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r", encoding="utf-8") as file:
            try:
                existing_data = json.load(file)
            except json.JSONDecodeError:
                existing_data = []
    else:
        existing_data = []

    existing_data.extend(data)

    with open(JSON_FILE, "w", encoding="utf-8") as file:
        json.dump(existing_data, file, indent=4)


def save_to_csv(data):
    """Saves extracted resume data into CSV file, creating one if it doesn't exist."""
    flattened_data = []

    for item in data:
        file_name = item.get("file_name", "Unknown")
        resume_details = item.get("resume_details", {})

        if not isinstance(resume_details, dict):
            resume_details = {"error": "Invalid resume details format"}

        flat_dict = {
            "file_name": file_name,
            "full_name": resume_details.get("full_name", ""),
            "Email": resume_details.get("email", ""),
            "title": resume_details.get("title", ""),
            "skills": "; ".join(resume_details.get("skills", [])),
            "error": resume_details.get("error", "")
        }

        # ✅ Handle projects properly (ensure it's a list)
        projects = resume_details.get("projects", [])

        if isinstance(projects, list) and projects:
            project_name = projects[0].get("name", "") if isinstance(projects[0], dict) else str(projects[0])
        else:
            project_name = str(projects)

        flat_dict["projects"] = project_name  # Always store as a string

        flattened_data.append(flat_dict)

    try:
        df = pd.DataFrame(flattened_data)

        # ✅ Check if CSV exists, if not create it
        file_exists = os.path.isfile(CSV_FILE)

        # ✅ Append to existing CSV or create new one
        df.to_csv(CSV_FILE, index=False, mode='a', header=not file_exists)
        print(f"✅ Successfully saved data to {CSV_FILE}")
        return True
    except Exception as e:
        print(f"❌ Error saving to CSV: {e}")
        return False


@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    """Handles multiple file uploads and extracts structured data."""
    if 'files' not in request.files:
        return jsonify({'error': 'No files part'}), 400

    files = request.files.getlist('files')

    if not files or all(file.filename == '' for file in files):
        return jsonify({'error': 'No selected files'}), 400

    extracted_data = []

    for file in files:
        try:
            pdf_path = f"uploaded_{file.filename}"
            file.save(pdf_path)

            text = _read_file_from_path(pdf_path)
            resume_data = extract_resume_sections(text)

            structured_output = {
                "file_name": file.filename,
                "resume_details": resume_data
            }
            extracted_data.append(structured_output)

        except Exception as e:
            structured_output = {
                "file_name": file.filename,
                "resume_details": {"error": f"Processing error: {str(e)}"}
            }
            extracted_data.append(structured_output)

    save_to_json(extracted_data)
    save_to_csv(extracted_data)

    return jsonify({
        'message': 'All files processed successfully',
        'resumes': extracted_data
    }), 200


if __name__ == '__main__':
    app.run(debug=True)