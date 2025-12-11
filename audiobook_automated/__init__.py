"""Main application package for AudiobookBay Automated."""

import os

from flask import Flask, Response, request

from .config import Config
from .extensions import csrf, executor, limiter, torrent_manager
from .routes import main_bp
from .scraper import network
from .utils import calculate_static_hash


def create_app(config_class: type[Config] = Config) -> Flask:
    """Create and configure a Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Validate critical configuration
    config_class.validate(app.logger)

    # OPTIMIZATION: Load pre-calculated static asset hash.
    # If the file exists (production build), use it to avoid disk I/O.
    # Otherwise, calculate it dynamically (local development).
    version_file = os.path.join(app.root_path, "version.txt")
    if os.path.exists(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            app.config["STATIC_VERSION"] = f.read().strip()
    else:
        static_folder = os.path.join(app.root_path, "static")
        app.config["STATIC_VERSION"] = calculate_static_hash(static_folder)

    # OPTIMIZATION: Calculate enabled status once at startup to avoid per-request logic
    abs_url = app.config.get("ABS_URL")
    abs_key = app.config.get("ABS_KEY")
    abs_lib = app.config.get("ABS_LIB")
    app.config["LIBRARY_RELOAD_ENABLED"] = all([abs_url, abs_key, abs_lib])

    # Initialize Extensions
    limiter.init_app(app)
    csrf.init_app(app)

    # Initialize TorrentManager with app configuration
    torrent_manager.init_app(app)

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
    def add_header(response: Response) -> Response:
        """Add Cache-Control headers to static files."""
        if request.path.startswith("/static"):
            response.headers["Cache-Control"] = "public, max-age=31536000"
        return response

    return app
