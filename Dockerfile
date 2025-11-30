# Use an official Python runtime as a parent image
FROM python:3.10.13-slim

# Set the working directory in the container
WORKDIR /app

# 1. Copy requirements first (from the app folder)
# This path is correct based on your new structure
COPY app/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy the 'app' folder contents
# This now automatically includes:
# app.py, clients.py, scraper.py, utils.py, healthcheck.py, static/, templates/
COPY app .

# 3. Copy the entrypoint script
# This is still in the root directory, so we copy it explicitly
COPY entrypoint.sh .

# Set permissions
RUN chmod +x entrypoint.sh

# Create a non-root user and switch to it for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 5078

# Use the bundled python script for health checks
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/healthcheck.py

# Define the command to run the application
CMD ["./entrypoint.sh"]