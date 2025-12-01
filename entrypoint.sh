#!/bin/sh

# Intelligent Bind Logic for Gunicorn
if [ -z "$LISTEN_HOST" ]; then
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

# Configure Gunicorn Timeout (Default 120s to handle slow scrapes/sleeps)
export TIMEOUT="${TIMEOUT:-120}"

echo "Starting Gunicorn with 1 worker and $THREADS threads."

# Run Gunicorn
# OPTIMIZATION: Added --preload. fast-fails on syntax errors and saves RAM.
# LOGGING: Explicitly route logs to stdout/stderr for Docker capture.
exec gunicorn --preload \
    --access-logfile - \
    --error-logfile - \
    --bind "${LISTEN_HOST}:${LISTEN_PORT}" \
    --workers 1 \
    --threads "$THREADS" \
    --timeout "$TIMEOUT" \
    app:app
