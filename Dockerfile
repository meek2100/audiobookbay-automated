# File: Dockerfile
# Use an official Python runtime as a parent image
# Using 3.14-slim as per project requirements (Current Stable).
FROM python:3.14-slim

# Labels for container registry metadata
LABEL org.opencontainers.image.title="audiobookbay-automated"
LABEL org.opencontainers.image.description="Automated AudiobookBay downloader and torrent manager"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/jamesry96/audiobookbay-automated"

# Install uv from official astral image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Prevent Python from writing .pyc files (saves space/io)
ENV PYTHONDONTWRITEBYTECODE=1
# Ensure logs are flushed immediately (easier debugging)
ENV PYTHONUNBUFFERED=1
# Ensure uv installs into system python environment
ENV UV_SYSTEM_PYTHON=1

# Set the working directory in the container
WORKDIR /app

# Install tzdata for correct timezone logging and gosu for user permission step-down
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata gosu && \
    rm -rf /var/lib/apt/lists/*

# 1. Copy project definition & lockfile
COPY pyproject.toml uv.lock ./
# 2. Install dependencies (Optimized for caching)
RUN mkdir -p audiobook_automated && \
    touch audiobook_automated/__init__.py && \
    uv pip install --no-cache . && \
    useradd -m appuser

# 3. Copy source code
COPY --chown=appuser:appuser audiobook_automated audiobook_automated/

# 4. Re-install package to include the actual source files
RUN uv pip install --no-cache --no-deps .

# 5. Copy scripts with correct ownership
COPY --chown=appuser:appuser entrypoint.sh .
# 6. Set permissions on scripts
RUN chmod +x entrypoint.sh

# Expose the port the app runs on
EXPOSE 5078

# Use the bundled python script for health checks
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 /app/audiobook_automated/healthcheck.py

# Define the command to run the application
ENTRYPOINT ["./entrypoint.sh"]

# CMD is empty by default; entrypoint.sh constructs the gunicorn command.
CMD []
