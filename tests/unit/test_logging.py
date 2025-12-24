# File: tests/unit/test_logging.py
"""Tests for logging configuration."""

import logging
from unittest.mock import MagicMock, patch

from audiobook_automated import create_app
from audiobook_automated.config import Config


class TestConfig(Config):
    """Minimal test config."""

    TESTING = True


def test_gunicorn_logger_inheritance() -> None:
    """Test that app logger inherits handlers from gunicorn.error if present.

    This covers the Gunicorn integration logic in __init__.py.
    """
    mock_gunicorn_logger = logging.getLogger("gunicorn.error")
    mock_handler = MagicMock()
    # CRITICAL FIX: Set the handler level to an integer.
    # Flask's has_level_handler compares handler.level <= logger.level.
    # If handler.level is a MagicMock, this raises TypeError.
    mock_handler.level = logging.INFO
    mock_gunicorn_logger.handlers = [mock_handler]
    mock_gunicorn_logger.setLevel(logging.ERROR)

    # We must patch getLogger to return our pre-configured mock when called inside create_app
    with patch("audiobook_automated.logging.getLogger", return_value=mock_gunicorn_logger):
        app = create_app(TestConfig)

        # Verify handlers were copied
        assert mock_handler in app.logger.handlers
        # Verify level was synced (TestConfig doesn't set LOG_LEVEL, so it takes gunicorn's)
        assert app.logger.level == logging.ERROR

    # Cleanup: Remove handlers from the global logger to avoid pollution
    mock_gunicorn_logger.handlers = []
