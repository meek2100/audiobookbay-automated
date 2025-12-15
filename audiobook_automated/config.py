"""Configuration module."""

import logging
import os


class Config:
    """Centralized configuration for the Flask application.

    Loads settings from environment variables with safe defaults.
    """

    # Core Flask Config
    # nosec B105: Default key is intentional for development; validation logic handles warning user.
    # noqa: S105  # Ruff flag for hardcoded password
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-to-a-secure-random-key")
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "0") == "1"
    TESTING: bool = os.getenv("TESTING", "0") == "1"

    # Static Asset Caching (1 Year)
    SEND_FILE_MAX_AGE_DEFAULT: int = 31536000

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
    LOG_LEVEL_STR: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_LEVEL: int = getattr(logging, LOG_LEVEL_STR, logging.INFO)

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
    # Handles parsing of the environment variable for page scraping limits.
    # Uses int(float(...)) to handle cases where env vars come in as "3.0".
    PAGE_LIMIT: int
    try:
        PAGE_LIMIT = int(float(os.getenv("PAGE_LIMIT", "3").strip()))
    except (ValueError, TypeError):
        PAGE_LIMIT = 3

    # Scraper Concurrency
    # Defines the number of worker threads for the scraping executor.
    SCRAPER_THREADS: int
    try:
        SCRAPER_THREADS = int(float(os.getenv("SCRAPER_THREADS", "3").strip()))
    except (ValueError, TypeError):
        SCRAPER_THREADS = 3

    # Scraper Request Timeout (Default 30)
    # Separated from Gunicorn timeout to ensure internal requests fail faster than the worker kill timer.
    SCRAPER_TIMEOUT: int
    try:
        SCRAPER_TIMEOUT = int(float(os.getenv("SCRAPER_TIMEOUT", "30").strip()))
    except (ValueError, TypeError):
        SCRAPER_TIMEOUT = 30

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
        if not hasattr(logging, cls.LOG_LEVEL_STR):
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
        if not cls.DL_CLIENT:
            logger.critical("Configuration Error: DL_CLIENT is missing.")
            raise ValueError("DL_CLIENT must be set to one of: qbittorrent, transmission, deluge")

        # Validate PAGE_LIMIT
        if cls.PAGE_LIMIT < 1:
            logger.warning(f"Invalid PAGE_LIMIT '{cls.PAGE_LIMIT}'. Resetting to 3.")
            cls.PAGE_LIMIT = 3

        # Validate DL_SCHEME
        if cls.DL_SCHEME not in ("http", "https"):
            logger.critical(f"Configuration Error: Invalid DL_SCHEME '{cls.DL_SCHEME}'. Must be 'http' or 'https'.")
            raise ValueError(f"Invalid DL_SCHEME '{cls.DL_SCHEME}'.")
