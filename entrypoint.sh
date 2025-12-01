#!/bin/sh

# Intelligent Bind Logic for Gunicorn
if [ -z "$LISTEN_HOST" ]; then
    # Use python to test if we can bind to IPv6 ::
    # If successful, use [::] (Gunicorn syntax for IPv6), else 0.0.0.0
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

# CONFIGURATION FOR RATE LIMITER & CONCURRENCY
# We default to 1 Worker and 8 Threads.
# This ensures that Flask-Limiter (using in-memory storage) correctly tracks
# requests across all threads. Multiple workers would split the limit counters.
export WORKERS="${WORKERS:-1}"
export THREADS="${THREADS:-8}"

# Configure Gunicorn Timeout (Default 120s to handle slow scrapes/sleeps)
export TIMEOUT="${TIMEOUT:-120}"

echo "Starting Gunicorn with $WORKERS worker(s) and $THREADS threads."

# Run Gunicorn
# usage: gunicorn --bind <ADDRESS>:<PORT> --workers <WORKERS> --threads <THREADS> --timeout <TIMEOUT> ...
exec gunicorn --bind "${LISTEN_HOST}:${LISTEN_PORT}" --workers "$WORKERS" --threads "$THREADS" --timeout "$TIMEOUT" app:app
