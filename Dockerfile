# Use an official Python runtime as a parent image
# Using 3.14-slim as per project requirements (Current Stable).
FROM python:3.14-slim

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

# Install tzdata for correct timezone logging and gosu for user permission step-down
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata gosu && \
    rm -rf /var/lib/apt/lists/*

# 1. Copy project definition
COPY pyproject.toml .
# 2. Install dependencies (Optimized for caching)
# We create a dummy directory structure so pip install .
# works for dependencies
# without invalidating the cache when source code changes later.
RUN mkdir -p audiobook_automated && \
    touch audiobook_automated/__init__.py && \
    pip install --no-cache-dir . && \
    useradd -m appuser

# 3. Copy source code
COPY audiobook_automated audiobook_automated/

# 4. Re-install package to include the actual source files
# The --no-deps flag ensures we don't re-check dependencies, keeping it fast.
RUN pip install --no-cache-dir --no-deps .

# 5. Copy scripts with correct ownership
COPY --chown=appuser:appuser entrypoint.sh .
# 6. Set permissions on scripts and generate version artifact
# Redirects the output of utils.py (the hash) to version.txt
RUN chmod +x entrypoint.sh && \
    python3 -m audiobook_automated.utils > audiobook_automated/version.txt

# Expose the port the app runs on
EXPOSE 5078

# Use the bundled python script for health checks
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/audiobook_automated/healthcheck.py

# Define the command to run the application
# ENTRYPOINT handles the switch to 'appuser' via gosu
ENTRYPOINT ["./entrypoint.sh"]

# CMD provides the default execution arguments
CMD ["gunicorn", "-c", "python:audiobook_automated.config", "audiobook_automated.app:app"]
