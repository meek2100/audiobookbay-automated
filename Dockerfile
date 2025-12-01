# Use an official Python runtime as a parent image
FROM python:3.10.13-slim

# Set the working directory in the container
WORKDIR /app

# 1. Copy project definition first
COPY pyproject.toml .

# 2. Install dependencies (creates a cached layer)
RUN pip install --no-cache-dir \
    "flask==3.1.2" \
    "requests==2.32.5" \
    "beautifulsoup4==4.14.3" \
    "qbittorrent-api==2025.11.1" \
    "python-dotenv==1.2.1" \
    "transmission-rpc==7.0.11" \
    "deluge-web-client==2.0.1" \
    "cachetools==6.2.2" \
    "gunicorn==23.0.0" \
    "Flask-WTF==1.2.2" \
    "Flask-Limiter==3.8.0"

# 3. Copy the source code
COPY app app/
COPY entrypoint.sh .

# 4. Install the app package
RUN pip install --no-cache-dir .

# Set permissions
RUN chmod +x entrypoint.sh

# Create a non-root user and switch to it for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 5078

# Use the bundled python script for health checks
# FIX: Point to the file inside the app/ directory
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/app/healthcheck.py

# Define the command to run the application
CMD ["./entrypoint.sh"]
