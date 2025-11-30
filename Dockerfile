# Use an official Python runtime as a parent image
FROM python:3.10.13-slim

# Set the working directory in the container
WORKDIR /app

# 1. Copy project definition and source code
# We copy the 'app' directory because 'pyproject.toml' needs to find the package source to install it.
COPY pyproject.toml .
COPY app app/
COPY entrypoint.sh .
COPY app/healthcheck.py .

# 2. Install the application and dependencies
# 'pip install .' reads pyproject.toml and installs dependencies AND the 'app' package itself.
RUN pip install --no-cache-dir .

# Set permissions
RUN chmod +x entrypoint.sh

# Create a non-root user and switch to it for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 5078

# Use the bundled python script for health checks
# Note: We now reference the copied healthcheck.py at root /app/healthcheck.py
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/healthcheck.py

# Define the command to run the application
CMD ["./entrypoint.sh"]
