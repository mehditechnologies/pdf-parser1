# Use an official Python runtime as a parent image
FROM python:3.9

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Tesseract-OCR
RUN apt-get update && apt-get install -y tesseract-ocr

# Expose port 8080
EXPOSE 8080

# Run the application
CMD ["gunicorn", "--timeout", "300", "--workers", "2", "--bind", "0.0.0.0:8080", "app:app"]
