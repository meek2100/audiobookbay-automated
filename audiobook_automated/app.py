# File: audiobook_automated/app.py
"""Entry point for the application."""

import logging

from . import create_app

logger = logging.getLogger(__name__)

# Create the application instance using the factory.
# This global 'app' variable is what Gunicorn looks for by default.
app = create_app()

if __name__ == "__main__":  # pragma: no cover
    # NOTE: This block is for local debugging only. Production uses entrypoint.sh.
    # Local Development Entry Point
    app.run(host=app.config["LISTEN_HOST"], port=app.config["LISTEN_PORT"])
