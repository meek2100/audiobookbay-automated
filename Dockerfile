# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Labels for container registry metadata
LABEL org.opencontainers.image.title="audiobookbay-automated"
LABEL org.opencontainers.image.description="Automated AudiobookBay downloader and torrent manager"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/jamesry96/audiobookbay-automated"

# OPTIMIZATION: Prevent Python from writing .pyc files (saves space/io)
ENV PYTHONDONTWRITEBYTECODE=1
# OPTIMIZATION: Ensure logs are flushed immediately (easier debugging)
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# OPTIMIZATION: Install tzdata for correct timezone logging
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    rm -rf /var/lib/apt/lists/*

# 1. Copy project definition first
COPY pyproject.toml .
# 2. Install dependencies (creates a cached layer)
RUN pip install --no-cache-dir .

# 3. Copy the source code
COPY app app/
COPY entrypoint.sh .
# 4. Set permissions
RUN chmod +x entrypoint.sh

# Create a non-root user and switch to it for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose the port the app runs on
EXPOSE 5078

# Use the bundled python script for health checks
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/app/healthcheck.py

# Define the command to run the application
CMD ["./entrypoint.sh"]
