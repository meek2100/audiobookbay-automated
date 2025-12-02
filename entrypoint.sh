#!/bin/sh

# Intelligent Bind Logic for Gunicorn
# If LISTEN_HOST is NOT set (null), perform auto-detection.
# If it is set (even to empty string), use it (allows users to disable/override logic).
if [ -z "${LISTEN_HOST:-}" ]; then
    if python3 -c "import socket; s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM); s.bind(('::', 0)); s.close()" 2>/dev/null; then
        export LISTEN_HOST="[::]"
        echo "Auto-detected IPv6 support. Binding Gunicorn to [::]"
    else
        export LISTEN_HOST="0.0.0.0"
        echo "IPv6 not available. Binding Gunicorn to 0.0.0.0"
    fi
else
    echo "Using user-defined LISTEN_HOST: $LISTEN_HOST"
fi

# Use default port 5078 if LISTEN_PORT env var is not set
export LISTEN_PORT="${LISTEN_PORT:-5078}"

# CONCURRENCY SETTINGS
# Worker count is hardcoded to 1 to ensure the in-memory rate limiter works correctly.
export THREADS="${THREADS:-8}"

# Configure Gunicorn Timeout (Default 60s to handle slow scrapes/sleeps, reduced from 120s)
export TIMEOUT="${TIMEOUT:-60}"

# LOGGING
# Ensure LOG_LEVEL is lowercase for Gunicorn config (e.g. "INFO" -> "info")
# Gunicorn is picky about lowercase log levels.
export LOG_LEVEL=$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')

# SAFETY: Explicitly default Flask Debug to 0 for production stability
export FLASK_DEBUG="${FLASK_DEBUG:-0}"

echo "Starting Gunicorn with 1 worker and $THREADS threads at log level $LOG_LEVEL."

# Run Gunicorn
# OPTIMIZATION: Added --preload. fast-fails on syntax errors and saves RAM.
# LOGGING: Explicitly route logs to stdout/stderr for Docker capture.
exec gunicorn --preload \
    --log-level "$LOG_LEVEL" \
    --access-logfile - \
    --error-logfile - \
    --bind "${LISTEN_HOST}:${LISTEN_PORT}" \
    --workers 1 \
    --threads "$THREADS" \
    --timeout "$TIMEOUT" \
    app:app
