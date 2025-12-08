"""Main application package for AudiobookBay Automated."""

import os

from flask import Flask, Response, request

from .config import Config
from .extensions import csrf, limiter, torrent_manager
from .routes import main_bp
from .utils import calculate_static_hash


def create_app(config_class: type[Config] = Config) -> Flask:
    """Create and configure a Flask application instance."""
    # Renamed to 'flask_app' to avoid name shadowing with the global 'app' import below
    flask_app = Flask(__name__)
    flask_app.config.from_object(config_class)

    # Validate critical configuration
    config_class.validate(flask_app.logger)

    # OPTIMIZATION: Calculate static asset hash once at startup.
    # This prevents hitting the disk (os.walk) on every single request.
    static_folder = os.path.join(flask_app.root_path, "static")
    flask_app.config["STATIC_VERSION"] = calculate_static_hash(static_folder)

    # Initialize Extensions
    limiter.init_app(flask_app)
    csrf.init_app(flask_app)

    # Initialize TorrentManager with app configuration
    torrent_manager.init_app(flask_app)

    # Initialize singleton managers (if they need app context or config)
    # TorrentManager loads config from env vars, so it doesn't strictly need init_app,
    # but we ensure it's ready.
    if not flask_app.config.get("TESTING"):
        torrent_manager.verify_credentials()

    # Register Blueprints
    flask_app.register_blueprint(main_bp)

    # OPTIMIZATION: Aggressive caching for static assets
    # Since we use versioning (?v=hash) in templates, we can safely tell
    # the browser to cache static files for a year (31536000 seconds).
    @flask_app.after_request
    def add_header(response: Response) -> Response:
        if request.path.startswith("/static"):
            response.headers["Cache-Control"] = "public, max-age=31536000"
        return response

    return flask_app
