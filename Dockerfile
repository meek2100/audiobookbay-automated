# Use an official Python runtime as a parent image
# Pinned to specific patch version for stability
FROM python:3.10.13-slim

# Set the working directory in the container
WORKDIR /app

# 1. Copy just the requirements first to leverage Docker cache
COPY app/requirements.txt .
# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy the rest of the application code
COPY app .

# 3. Copy scripts
COPY entrypoint.sh .
COPY healthcheck.py .

# Set permissions
RUN chmod +x entrypoint.sh

# Create a non-root user and switch to it for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 5078

# Use the bundled python script for health checks
# We simply call the python script, which handles the logic and exit codes
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/healthcheck.py

# Define the command to run the application using the intelligent entrypoint
CMD ["./entrypoint.sh"]