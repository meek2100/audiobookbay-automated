# File: audiobook_automated/__init__.py
"""Main application package for AudiobookBay Automated."""

import logging
from pathlib import Path
from typing import Any

from flask import Flask, Response, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import csrf, executor, limiter, register_shutdown_handlers, talisman, torrent_manager
from .routes import main_bp
from .scraper import network
from .utils import get_application_version


def create_app(config_class: type[Config] = Config) -> Flask:
    """Create and configure a Flask application instance."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Validate critical configuration
    config_class.validate(app.logger)

    if app.debug:
        app.logger.warning("Running in DEBUG mode. Security checks may be bypassed.")

    # PRODUCTION FIX: Log Level Inheritance
    configured_level = app.config.get("LOG_LEVEL")
    _configure_logging(app, configured_level)

    # OPTIMIZATION: Static Asset Versioning Strategy
    # Priority:
    # 1. Config/Env Var (Developer Override)
    # 2. version.txt (Docker Build Artifact)
    # 3. Dynamic Calculation (Local Development Fallback)

    if not app.config.get("STATIC_VERSION"):
        static_folder = Path(app.root_path) / "static"
        app.config["STATIC_VERSION"] = get_application_version(static_folder)

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
        content_security_policy_nonce_in=["script-src"],
        # FIX: Allow HTTP in dev/test, force HTTPS in prod if needed (usually handled by proxy)
        force_https=app.config["FORCE_HTTPS"],
        # FIX: Ensure Talisman respects the config for Secure cookies (needed for HTTP access)
        session_cookie_secure=app.config["SESSION_COOKIE_SECURE"],
    )

    # Initialize TorrentManager with app configuration
    torrent_manager.init_app(app)
    # RESOURCE SAFETY: Ensure thread-local sessions are closed after each request
    # REMOVED: app.teardown_appcontext(torrent_manager.teardown_request) to prevent connection storm

    # HEALTH CHECK: Verify torrent client connection at startup.
    # This allows admins to see immediate feedback in logs if the client is unreachable.
    # We do NOT block startup, as the app should remain accessible for debugging.
    if not torrent_manager.verify_credentials():
        app.logger.warning("Startup Check: Torrent client is NOT connected. Downloads will fail until resolved.")

    # Initialize Scraper Executor
    executor.init_app(app)

    # GRACEFUL SHUTDOWN: Register signal handlers
    register_shutdown_handlers(app)

    # SYNCHRONIZATION: Initialize Global Request Semaphore
    # This must be done here to avoid circular imports in extensions.py
    max_workers = app.config.get("SCRAPER_THREADS", 3)
    network.init_semaphore(max_workers)

    # Register Blueprints
    app.register_blueprint(main_bp)

    @app.context_processor
    def inject_global_vars() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        """Inject global configuration variables into all templates."""
        return {
            "site_title": app.config["SITE_TITLE"],
            "site_logo": app.config.get("SITE_LOGO"),
            "splash_enabled": app.config["SPLASH_ENABLED"],
            "splash_title": app.config["SPLASH_TITLE"],
            "splash_message": app.config["SPLASH_MESSAGE"],
            "splash_duration": app.config["SPLASH_DURATION"],
        }

    # OPTIMIZATION: Aggressive caching for static assets
    # Since we use versioning (?v=hash) in templates, we can safely tell
    # the browser to cache static files for a year (31536000 seconds).
    @app.after_request
    def add_header(response: Response) -> Response:  # pyright: ignore[reportUnusedFunction]
        """Add Cache-Control headers to static files."""
        if request.path.startswith("/static"):
            response.headers["Cache-Control"] = "public, max-age=31536000"
        return response

    # FIX: CSRF 400 Error - Zero Cookies Issue
    # Force Flask to set the session cookie on the first request if it's missing.
    # This addresses cases where the browser doesn't send the cookie back (e.g. IP access).
    @app.after_request
    def ensure_session_cookie(response: Response) -> Response:  # pyright: ignore[reportUnusedFunction]
        """Ensure session cookie is set if missing."""
        if not request.cookies.get(app.config["SESSION_COOKIE_NAME"]):
            session.modified = True
        return response

    # ProxyFix for Docker/Ingress
    if not app.debug:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    return app


def _configure_logging(app: Flask, configured_level: int | None) -> None:
    """Configure application logging, inheriting from Gunicorn if available.

    Args:
        app: The Flask application instance.
        configured_level: The explicitly configured log level (or None).
    """
    # Priority:
    # 1. Configured LOG_LEVEL (if set in env)
    # 2. Gunicorn Logger Level (if running in Gunicorn)
    # 3. Default (INFO)

    # DEPLOYMENT FIX: Attach Gunicorn handlers if running in production
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
