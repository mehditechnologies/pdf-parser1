# Use official Python image as the base
FROM python:3.10

# Install system dependencies for Tesseract and PDF processing
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils

# Set the working directory in the container
WORKDIR /app

# Copy all project files into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port Flask runs on
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=app.py

# Start the Flask app with Gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]
