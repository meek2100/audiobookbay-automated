# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# 1. Copy just the requirements first.
# This allows Docker to cache the installed packages if requirements.txt hasn't changed.
COPY app/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy the rest of the application code
COPY app .

# Expose the port the app runs on
EXPOSE 5078

# Define the command to run the application using Gunicorn for production
# --workers 4: Handles 4 concurrent requests
# --bind 0.0.0.0:5078: Listens on all interfaces at port 5078
# app:app : Refers to the module 'app' (app.py) and the flask instance 'app'
CMD ["gunicorn", "--bind", "0.0.0.0:5078", "--workers", "4", "app:app"]