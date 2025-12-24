# File: audiobook_automated/__init__.py
"""Main application package for AudiobookBay Automated."""

import logging
import os

from flask import Flask, Response, request

from .config import Config
from .extensions import csrf, executor, limiter, talisman, torrent_manager
from .routes import main_bp
from .scraper import network
from .utils import calculate_static_hash


def create_app(config_class: type[Config] = Config) -> Flask:
    """Create and configure a Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Validate critical configuration
    config_class.validate(app.logger)

    # PRODUCTION FIX: Log Level Inheritance
    # Priority:
    # 1. Configured LOG_LEVEL (if set in env)
    # 2. Gunicorn Logger Level (if running in Gunicorn)
    # 3. Default (INFO)

    configured_level = app.config.get("LOG_LEVEL")

    # DEPLOYMENT FIX: Attach Gunicorn handlers if running in production
    # Gunicorn creates its own logger ('gunicorn.error'), and without this,
    # Flask application logs might not appear in the container stdout/stderr.
    gunicorn_logger = logging.getLogger("gunicorn.error")
    if gunicorn_logger.handlers:
        app.logger.handlers = gunicorn_logger.handlers
        # Sync level to match Gunicorn (unless overridden by config)
        if configured_level is not None:
            app.logger.setLevel(configured_level)
        else:
            app.logger.setLevel(gunicorn_logger.level)
    else:
        # Local/Dev mode or non-Gunicorn runner
        app.logger.setLevel(configured_level if configured_level is not None else logging.INFO)

    # OPTIMIZATION: Static Asset Versioning Strategy
    # Priority:
    # 1. Config/Env Var (Developer Override)
    # 2. version.txt (Docker Build Artifact)
    # 3. Dynamic Calculation (Local Development Fallback)

    if not app.config.get("STATIC_VERSION"):
        version_file = os.path.join(app.root_path, "version.txt")
        if os.path.exists(version_file):
            try:
                with open(version_file, encoding="utf-8") as f:
                    app.config["STATIC_VERSION"] = f.read().strip()
            except OSError:
                app.logger.warning("Failed to read version.txt, falling back to calculation.")
                static_folder = os.path.join(app.root_path, "static")
                app.config["STATIC_VERSION"] = calculate_static_hash(static_folder)
        else:
            static_folder = os.path.join(app.root_path, "static")
            app.config["STATIC_VERSION"] = calculate_static_hash(static_folder)

    # Initialize Extensions
    limiter.init_app(app)
    csrf.init_app(app)

    # Initialize Security Headers
    # We must allow 'unsafe-inline' for style-src because of the dynamic nature of
    # some UI components, but we restrict scripts strictly.
    # We also allow images from any source (*) because cover images come from random mirrors.
    csp = {
        "default-src": ["'self'"],
        "img-src": ["'self'", "*", "data:"],
        "style-src": ["'self'", "'unsafe-inline'"],
        # Add 'unsafe-eval' only if strictly needed by libraries like Flatpickr,
        # otherwise keep strict.
        "script-src": ["'self'"],
    }
    talisman.init_app(
        app,
        content_security_policy=csp,
        # Allow HTTP in dev/test, force HTTPS in prod if needed (usually handled by proxy)
        force_https=not (app.config["TESTING"] or app.config["FLASK_DEBUG"]),
    )

    # Initialize TorrentManager with app configuration
    torrent_manager.init_app(app)

    # HEALTH CHECK: Verify torrent client connection at startup.
    # This allows admins to see immediate feedback in logs if the client is unreachable.
    # We do NOT block startup, as the app should remain accessible for debugging.
    if not torrent_manager.verify_credentials():
        app.logger.warning("Startup Check: Torrent client is NOT connected. Downloads will fail until resolved.")

    # Initialize Scraper Executor
    executor.init_app(app)

    # SYNCHRONIZATION: Initialize Global Request Semaphore
    # This must be done here to avoid circular imports in extensions.py
    max_workers = app.config.get("SCRAPER_THREADS", 3)
    network.init_semaphore(max_workers)

    # Register Blueprints
    app.register_blueprint(main_bp)

    # OPTIMIZATION: Aggressive caching for static assets
    # Since we use versioning (?v=hash) in templates, we can safely tell
    # the browser to cache static files for a year (31536000 seconds).
    @app.after_request
    def add_header(response: Response) -> Response:  # pyright: ignore[reportUnusedFunction]
        """Add Cache-Control headers to static files."""
        if request.path.startswith("/static"):
            response.headers["Cache-Control"] = "public, max-age=31536000"
        return response

    return app
