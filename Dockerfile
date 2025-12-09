# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Labels for container registry metadata
LABEL org.opencontainers.image.title="audiobookbay-automated"
LABEL org.opencontainers.image.description="Automated AudiobookBay downloader and torrent manager"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/jamesry96/audiobookbay-automated"

# Prevent Python from writing .pyc files (saves space/io)
ENV PYTHONDONTWRITEBYTECODE=1
# Ensure logs are flushed immediately (easier debugging)
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install tzdata for correct timezone logging
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    rm -rf /var/lib/apt/lists/*

# 1. Copy project definition first
COPY pyproject.toml .

# 2. Install dependencies and create user in a single layer (Fixes DL3059)
# We create the user here to ensure it exists before we COPY files with ownership
RUN pip install --no-cache-dir . && \
    useradd -m appuser

# 3. Copy the source code with correct ownership (Avoids huge chown layer)
COPY --chown=appuser:appuser app app/
COPY --chown=appuser:appuser entrypoint.sh .

# 4. Set permissions on scripts and verify utils
RUN chmod +x entrypoint.sh && \
    python3 -m app.utils

# Switch to non-root user for security
USER appuser

# Expose the port the app runs on
EXPOSE 5078

# Use the bundled python script for health checks
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/app/healthcheck.py

# Define the command to run the application
CMD ["./entrypoint.sh"]
