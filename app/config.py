"""Configuration module."""

import logging
import os
import sys


class Config:
    """Centralized configuration for the Flask application.

    Loads settings from environment variables with safe defaults.
    """

    # Core Flask Config
    # nosec B105: Default key is intentional for development; validation logic handles warning user.
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-to-a-secure-random-key")
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
    TESTING = os.getenv("TESTING", "0") == "1"

    # Static Asset Caching (1 Year)
    SEND_FILE_MAX_AGE_DEFAULT = 31536000

    # File System
    SAVE_PATH_BASE = os.getenv("SAVE_PATH_BASE")

    # Integrations
    ABS_URL = os.getenv("ABS_URL")
    ABS_KEY = os.getenv("ABS_KEY")
    ABS_LIB = os.getenv("ABS_LIB")

    # UI Customization
    NAV_LINK_NAME = os.getenv("NAV_LINK_NAME")
    NAV_LINK_URL = os.getenv("NAV_LINK_URL")

    # Logging
    LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

    # Scraper Configuration
    ABB_HOSTNAME = os.getenv("ABB_HOSTNAME", "audiobookbay.lu").strip(" \"'")

    # Parse comma-separated mirrors into a list
    _mirrors_str = os.getenv("ABB_MIRRORS", "")
    ABB_MIRRORS = [m.strip() for m in _mirrors_str.split(",") if m.strip()]

    # Parse comma-separated trackers into a list
    _trackers_str = os.getenv("MAGNET_TRACKERS", "")
    MAGNET_TRACKERS = [t.strip() for t in _trackers_str.split(",") if t.strip()]

    # Page Limit (Default 3)
    try:
        PAGE_LIMIT = int(os.getenv("PAGE_LIMIT", "3").strip())
    except ValueError:
        PAGE_LIMIT = 3

    @classmethod
    def validate(cls, logger: logging.Logger) -> None:
        """Validate critical configuration at startup."""
        if cls.SECRET_KEY == "change-this-to-a-secure-random-key":  # nosec B105
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
                sys.exit(1)
        else:
            logger.info(f"SAVE_PATH_BASE configured as: {cls.SAVE_PATH_BASE}")
            logger.info(
                "Reminder: This path must exist inside the TORRENT CLIENT container, "
                "not necessarily this application's container."
            )

        # Validate PAGE_LIMIT
        if cls.PAGE_LIMIT < 1:
            logger.warning(f"Invalid PAGE_LIMIT '{cls.PAGE_LIMIT}'. Resetting to 3.")
            cls.PAGE_LIMIT = 3
