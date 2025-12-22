# File: audiobook_automated/config.py
"""Configuration module."""

import logging
import os


def _parse_env_int(key: str, default: int) -> int:
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
        return int(float(raw.strip()))
    except (ValueError, TypeError):
        return default


def _parse_env_bool(key: str, default: bool = False) -> bool:
    """Parse a boolean environment variable safely.

    Supports '1', 'true', 'yes', 'on' (case-insensitive) as True.

    Args:
        key: The environment variable key.
        default: The default value if missing.

    Returns:
        bool: The parsed boolean.
    """
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Config:
    """Centralized configuration for the Flask application.

    Loads settings from environment variables with safe defaults.
    """

    # Core Flask Config
    # nosec B105: Default key is intentional for development; validation logic handles warning user.
    # noqa: S105  # Ruff flag for hardcoded password
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-to-a-secure-random-key")
    FLASK_DEBUG: bool = _parse_env_bool("FLASK_DEBUG", False)
    TESTING: bool = _parse_env_bool("TESTING", False)

    # Static Asset Caching (1 Year)
    SEND_FILE_MAX_AGE_DEFAULT: int = 31536000

    # Static Version Override (Optional)
    # Allows developers to force a version string via .env, overriding the Docker build hash.
    STATIC_VERSION: str | None = os.getenv("STATIC_VERSION")

    # File System
    SAVE_PATH_BASE: str | None = os.getenv("SAVE_PATH_BASE")

    # Integrations
    ABS_URL: str | None = os.getenv("ABS_URL")
    ABS_KEY: str | None = os.getenv("ABS_KEY")
    ABS_LIB: str | None = os.getenv("ABS_LIB")

    # UI Customization
    NAV_LINK_NAME: str | None = os.getenv("NAV_LINK_NAME")
    NAV_LINK_URL: str | None = os.getenv("NAV_LINK_URL")

    # Torrent Client Configuration
    DL_CLIENT: str | None = os.getenv("DL_CLIENT")
    DL_HOST: str | None = os.getenv("DL_HOST")
    DL_PORT: str | None = os.getenv("DL_PORT")
    DL_USERNAME: str | None = os.getenv("DL_USERNAME")
    DL_PASSWORD: str | None = os.getenv("DL_PASSWORD")
    DL_CATEGORY: str = os.getenv("DL_CATEGORY", "abb-automated")
    DL_SCHEME: str = os.getenv("DL_SCHEME", "http")
    DL_URL: str | None = os.getenv("DL_URL")

    # Logging
    # We allow LOG_LEVEL to be None if unset to support Gunicorn level inheritance in __init__.py.
    _log_level_env: str | None = os.getenv("LOG_LEVEL")
    LOG_LEVEL_STR: str = _log_level_env.upper() if _log_level_env else "INFO"
    # Logic: If Env is set, resolve it (defaulting to INFO if invalid string). If not set, leave as None.
    LOG_LEVEL: int | None = getattr(logging, LOG_LEVEL_STR, logging.INFO) if _log_level_env else None

    # Scraper Configuration
    # ROBUSTNESS: Fallback if env var is set but empty string
    _hostname: str = os.getenv("ABB_HOSTNAME", "audiobookbay.lu").strip(" \"'")
    ABB_HOSTNAME: str = _hostname if _hostname else "audiobookbay.lu"

    # Parse comma-separated mirrors into a list
    _mirrors_str: str = os.getenv("ABB_MIRRORS", "")
    ABB_MIRRORS: list[str] = [m.strip() for m in _mirrors_str.split(",") if m.strip()]

    # Parse comma-separated trackers into a list
    _trackers_str: str = os.getenv("MAGNET_TRACKERS", "")
    MAGNET_TRACKERS: list[str] = [t.strip() for t in _trackers_str.split(",") if t.strip()]

    # Page Limit (Default 3)
    PAGE_LIMIT: int = _parse_env_int("PAGE_LIMIT", 3)

    # Scraper Concurrency
    # Defines the number of worker threads for the scraping executor.
    SCRAPER_THREADS: int = _parse_env_int("SCRAPER_THREADS", 3)

    # Scraper Request Timeout (Default 30)
    # Separated from Gunicorn timeout to ensure internal requests fail faster than the worker kill timer.
    SCRAPER_TIMEOUT: int = _parse_env_int("SCRAPER_TIMEOUT", 30)

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

        # Validate DL_SCHEME
        if cls.DL_SCHEME not in ("http", "https"):
            logger.critical(f"Configuration Error: Invalid DL_SCHEME '{cls.DL_SCHEME}'. Must be 'http' or 'https'.")
            raise ValueError(f"Invalid DL_SCHEME '{cls.DL_SCHEME}'.")
