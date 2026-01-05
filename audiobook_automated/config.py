# File: audiobook_automated/config.py
"""Configuration module."""

import logging
import os

from .constants import DEFAULT_SITE_TITLE, DEFAULT_SPLASH_MESSAGE
from .utils import parse_bool


def parse_env_int(key: str, default: int) -> int:
    """Parse an integer environment variable safely.

    Handles cases where values might be passed as float strings (e.g., "3.0")
    by container orchestrators.

    Args:
        key: The environment variable key.
        default: The default value if missing or invalid.

    Returns:
        int: The parsed integer.
    """
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(float(raw.strip().strip("'\"")))
    except (ValueError, TypeError, OverflowError):
        return default


class Config:
    """Centralized configuration for the Flask application.

    Loads settings from environment variables with safe defaults.
    """

    # Core Flask Config
    # nosec B105: Default key is intentional for development; validation logic handles warning user.
    # noqa: S105  # Ruff flag for hardcoded password
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-to-a-secure-random-key").strip(" \"'")
    FLASK_DEBUG: bool = parse_bool(os.getenv("FLASK_DEBUG"), False)
    TESTING: bool = parse_bool(os.getenv("TESTING"), False)

    # Static Asset Caching (1 Year)
    SEND_FILE_MAX_AGE_DEFAULT: int = 31536000

    # Static Version Override (Optional)
    # Allows developers to force a version string via .env, overriding the Docker build hash.
    _static_version: str | None = os.getenv("STATIC_VERSION")
    STATIC_VERSION: str | None = _static_version.strip(" \"'") if _static_version else None

    # File System
    _save_path_base: str | None = os.getenv("SAVE_PATH_BASE")
    SAVE_PATH_BASE: str | None = _save_path_base.strip(" \"'") if _save_path_base else None

    # Integrations
    _abs_url: str | None = os.getenv("ABS_URL")
    ABS_URL: str | None = _abs_url.strip(" \"'") if _abs_url else None
    _abs_key: str | None = os.getenv("ABS_KEY")
    ABS_KEY: str | None = _abs_key.strip(" \"'") if _abs_key else None
    _abs_lib: str | None = os.getenv("ABS_LIB")
    ABS_LIB: str | None = _abs_lib.strip(" \"'") if _abs_lib else None

    # UI Customization
    _nav_link_name: str | None = os.getenv("NAV_LINK_NAME")
    NAV_LINK_NAME: str | None = _nav_link_name.strip(" \"'") if _nav_link_name else None
    _nav_link_url: str | None = os.getenv("NAV_LINK_URL")
    NAV_LINK_URL: str | None = _nav_link_url.strip(" \"'") if _nav_link_url else None

    # HTTPS Configuration
    # Defaults to False to ensure local deployments work out-of-the-box.
    FORCE_HTTPS: bool = parse_bool(os.getenv("FORCE_HTTPS"), False)

    # Session & CSRF Configuration
    SESSION_COOKIE_NAME: str = "audiobook_session"
    SESSION_COOKIE_SAMESITE: str = "Lax"
    # Force Secure=False to allow cookies over HTTP/IP as requested
    SESSION_COOKIE_SECURE: bool = False
    WTF_CSRF_SSL_STRICT: bool = FORCE_HTTPS

    # Listen Host/Port
    # nosec B104: Default to all interfaces for Docker container usage
    LISTEN_HOST: str = os.getenv("LISTEN_HOST", "0.0.0.0").strip(" \"'")  # noqa: S104
    LISTEN_PORT: int = parse_env_int("LISTEN_PORT", 5078)

    # Torrent Client Configuration
    _dl_client: str | None = os.getenv("DL_CLIENT")
    DL_CLIENT: str | None = _dl_client.strip(" \"'") if _dl_client else None
    _dl_host: str | None = os.getenv("DL_HOST")
    DL_HOST: str | None = _dl_host.strip(" \"'") if _dl_host else None
    _dl_port: str | None = os.getenv("DL_PORT")
    DL_PORT: str | None = _dl_port.strip(" \"'") if _dl_port else None
    _dl_username: str | None = os.getenv("DL_USERNAME")
    DL_USERNAME: str | None = _dl_username.strip(" \"'") if _dl_username else None
    _dl_password: str | None = os.getenv("DL_PASSWORD")
    DL_PASSWORD: str | None = _dl_password.strip(" \"'") if _dl_password else None
    DL_CATEGORY: str = os.getenv("DL_CATEGORY", "abb-automated").strip(" \"'")
    DL_SCHEME: str = os.getenv("DL_SCHEME", "http").strip(" \"'")
    _dl_url: str | None = os.getenv("DL_URL")
    DL_URL: str | None = _dl_url.strip(" \"'") if _dl_url else None
    DL_CLIENT_OS: str = os.getenv("DL_CLIENT_OS", "posix").strip(" \"'").lower()

    # Logging
    # We allow LOG_LEVEL to be None if unset to support Gunicorn level inheritance in __init__.py.
    _log_level_raw: str | None = os.getenv("LOG_LEVEL")
    _log_level_env: str | None = _log_level_raw.strip(" \"'") if _log_level_raw else None
    LOG_LEVEL_STR: str = _log_level_env.upper() if _log_level_env else "INFO"
    # Logic: If Env is set, resolve it (defaulting to INFO if invalid string). If not set, leave as None.
    LOG_LEVEL: int | None = getattr(logging, LOG_LEVEL_STR, logging.INFO) if _log_level_env else None

    # Scraper Configuration
    # ROBUSTNESS: Fallback if env var is set but empty string
    _hostname: str = os.getenv("ABB_HOSTNAME", "audiobookbay.lu").strip(" \"'")
    ABB_HOSTNAME: str = _hostname if _hostname else "audiobookbay.lu"

    # Parse comma-separated mirrors into a list
    # Strip the whole string first in case the list is quoted: "a.com,b.com"
    _mirrors_str: str = os.getenv("ABB_MIRRORS", "").strip(" \"'")
    ABB_MIRRORS: list[str] = [m.strip() for m in _mirrors_str.split(",") if m.strip()]

    # Parse comma-separated trackers into a list
    _trackers_str: str = os.getenv("MAGNET_TRACKERS", "").strip(" \"'")
    MAGNET_TRACKERS: list[str] = [t.strip() for t in _trackers_str.split(",") if t.strip()]

    # Page Limit (Default 3)
    PAGE_LIMIT: int = parse_env_int("PAGE_LIMIT", 3)

    # Scraper Concurrency
    # Defines the number of worker threads for the scraping executor.
    SCRAPER_THREADS: int = parse_env_int("SCRAPER_THREADS", 3)

    # Scraper Request Timeout (Default 30)
    # Separated from Gunicorn timeout to ensure internal requests fail faster than the worker kill timer.
    SCRAPER_TIMEOUT: int = parse_env_int("SCRAPER_TIMEOUT", 30)

    # Torrent Client Timeout (Default 30)
    CLIENT_TIMEOUT: int = parse_env_int("CLIENT_TIMEOUT", 30)

    # Site Identity
    SITE_TITLE: str = os.getenv("SITE_TITLE", DEFAULT_SITE_TITLE).strip(" \"'")
    _site_logo: str | None = os.getenv("SITE_LOGO")
    SITE_LOGO: str | None = _site_logo.strip(" \"'") if _site_logo else None

    # Splash Screen Configuration
    SPLASH_ENABLED: bool = parse_bool(os.getenv("SPLASH_ENABLED"), True)
    # Fallback to SITE_TITLE if SPLASH_TITLE is not explicitly set
    SPLASH_TITLE: str = os.getenv("SPLASH_TITLE", SITE_TITLE).strip(" \"'")
    SPLASH_MESSAGE: str = os.getenv("SPLASH_MESSAGE", DEFAULT_SPLASH_MESSAGE).strip(" \"'")
    SPLASH_DURATION: int = parse_env_int("SPLASH_DURATION", 4500)

    @property
    def LIBRARY_RELOAD_ENABLED(self) -> bool:
        """Determine if Audiobookshelf integration is enabled.

        Returns:
            bool: True if all required ABS configuration values are present, False otherwise.
        """
        return all([self.ABS_URL, self.ABS_KEY, self.ABS_LIB])

    @classmethod
    def validate(cls, logger: logging.Logger) -> None:
        """Validate critical configuration at startup."""
        # nosec B105
        # The following line triggers S105/B105 but is intentional for validation.
        if cls.SECRET_KEY == "change-this-to-a-secure-random-key":  # noqa: S105
            if cls.FLASK_DEBUG or cls.TESTING:
                logger.warning(
                    "WARNING: You are using the default insecure SECRET_KEY. "
                    "This is acceptable for development/testing but UNSAFE for production."
                )
            else:
                logger.critical(
                    "CRITICAL SECURITY ERROR: You are running in PRODUCTION with the default insecure SECRET_KEY."
                )
                raise ValueError(
                    "Application refused to start: Change SECRET_KEY in your .env file for production deployment."
                )

        # Validate LOG_LEVEL
        # Only validate if the user actually tried to set it
        if cls._log_level_env and not hasattr(logging, cls.LOG_LEVEL_STR):
            logger.warning(
                f"Configuration Warning: Invalid LOG_LEVEL '{cls.LOG_LEVEL_STR}' provided. Defaulting to INFO."
            )

        # Validate SAVE_PATH_BASE
        if not cls.SAVE_PATH_BASE:
            if not cls.TESTING:
                logger.critical("Configuration Error: SAVE_PATH_BASE is missing.")
                # Raise RuntimeError instead of sys.exit(1) to allow WSGI servers to log the error properly
                raise RuntimeError("Configuration Error: SAVE_PATH_BASE is missing.")
        else:
            logger.info(f"SAVE_PATH_BASE configured as: {cls.SAVE_PATH_BASE}")
            logger.info(
                "Reminder: This path must exist inside the TORRENT CLIENT container, "
                "not necessarily this application's container."
            )

        # Validate DL_CLIENT
        # RELAXED VALIDATION: We now allow any string to support drop-in plugins.
        # The Manager will fail later if the module doesn't exist.
        if not cls.DL_CLIENT:
            logger.critical("Configuration Error: DL_CLIENT is missing.")
            raise ValueError("DL_CLIENT must be set.")

        # Validate PAGE_LIMIT
        if cls.PAGE_LIMIT < 1:
            logger.warning(f"Invalid PAGE_LIMIT '{cls.PAGE_LIMIT}'. Resetting to 3.")
            cls.PAGE_LIMIT = 3
        elif cls.PAGE_LIMIT > 10:  # noqa: PLR2004
            logger.warning(f"PAGE_LIMIT '{cls.PAGE_LIMIT}' is too high. Capping at 10 to prevent DoS.")
            cls.PAGE_LIMIT = 10

        # Validate DL_SCHEME
        if cls.DL_SCHEME not in ("http", "https"):
            logger.critical(f"Configuration Error: Invalid DL_SCHEME '{cls.DL_SCHEME}'. Must be 'http' or 'https'.")
            raise ValueError(f"Invalid DL_SCHEME '{cls.DL_SCHEME}'.")
