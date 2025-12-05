import logging
import os
import sys


class Config:
    """
    Centralized configuration for the Flask application.
    Loads settings from environment variables with safe defaults.
    """

    # Core Flask Config
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
    # Robustly handle case-sensitivity from Env vars (e.g. "info", "INFO", "Info")
    LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
    # Fallback to INFO if the string is not a valid logging level attribute
    # Note: Explicit validation occurs in the validate method below.
    LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

    @classmethod
    def validate(cls, logger):
        """
        Validates critical configuration at startup.
        """
        if cls.SECRET_KEY == "change-this-to-a-secure-random-key":
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

        if not cls.SAVE_PATH_BASE:
            if not cls.TESTING:
                logger.critical("Configuration Error: SAVE_PATH_BASE is missing.")
                sys.exit(1)
        else:
            # Informative log for debugging common Docker path mapping issues
            logger.info(f"SAVE_PATH_BASE configured as: {cls.SAVE_PATH_BASE}")
            logger.info(
                "Reminder: This path must exist inside the TORRENT CLIENT container, "
                "not necessarily this application's container."
            )
