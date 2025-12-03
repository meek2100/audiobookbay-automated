from flask import Flask

from .config import Config
from .extensions import csrf, limiter, torrent_manager
from .routes import main_bp


def create_app(config_class=Config):
    """
    Application Factory: Creates and configures a Flask application instance.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Validate critical configuration
    config_class.validate(app.logger)

    # Initialize Extensions
    limiter.init_app(app)
    csrf.init_app(app)

    # Initialize singleton managers (if they need app context or config)
    # TorrentManager loads config from env vars, so it doesn't strictly need init_app,
    # but we ensure it's ready.
    if not app.config.get("TESTING"):
        torrent_manager.verify_credentials()

    # Register Blueprints
    app.register_blueprint(main_bp)

    return app


# Expose the 'app' instance from app.py to maintain compatibility with
# Gunicorn commands that expect 'app:app' (module:variable).
# This import must be at the bottom to avoid circular dependency errors
# during the initial import of create_app.
