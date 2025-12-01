# Expose the Flask application instance to allow 'gunicorn app:app' to work
from .app import app

__all__ = ["app"]
