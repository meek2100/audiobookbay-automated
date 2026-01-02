# File: tests/unit/test_startup.py
"""Unit tests for application startup logic."""

import logging
from pathlib import Path
from unittest import mock

import pytest

from audiobook_automated import create_app
from audiobook_automated.config import Config


@pytest.fixture
def mock_version_file(tmp_path: Path) -> Path:
    """Create a temporary version.txt file."""
    version_file = tmp_path / "version.txt"
    version_file.write_text("v1.2.3-test", encoding="utf-8")
    return version_file


def test_create_app_uses_version_file() -> None:
    """Test that create_app reads from version.txt if present."""
    # Mock os.path.exists to return True for version.txt
    # Mock open to return "v1.2.3-test"
    with (
        mock.patch("os.path.exists", return_value=True),
        mock.patch("builtins.open", mock.mock_open(read_data="v1.2.3-test")),
        mock.patch("audiobook_automated.calculate_static_hash") as mock_calc,
        mock.patch("audiobook_automated.clients.manager.TorrentManager.verify_credentials", return_value=True),
    ):
        app = create_app()
        assert app.config["STATIC_VERSION"] == "v1.2.3-test"
        mock_calc.assert_not_called()


def test_create_app_fallback_hash() -> None:
    """Test that create_app falls back to hash calculation if version.txt is missing."""
    # Mock os.path.exists to return False
    with (
        mock.patch("os.path.exists", return_value=False),
        mock.patch("audiobook_automated.calculate_static_hash") as mock_calc,
        mock.patch("audiobook_automated.clients.manager.TorrentManager.verify_credentials", return_value=True),
    ):
        mock_calc.return_value = "hash123"
        app = create_app()
        assert app.config["STATIC_VERSION"] == "hash123"
        mock_calc.assert_called()


def test_create_app_invalid_config() -> None:
    """Test that create_app raises ValueError for invalid config (e.g. secret key)."""

    class BadConfig(Config):
        SECRET_KEY = "change-this-to-a-secure-random-key"
        FLASK_DEBUG = False  # Production mode
        TESTING = False  # Ensure Testing mode is OFF to trigger the check

    # We expect a ValueError because the default secret key is unsafe for prod
    with mock.patch("audiobook_automated.clients.manager.TorrentManager.verify_credentials", return_value=True):
        with pytest.raises(ValueError, match="Application refused to start"):
            create_app(BadConfig)


def test_log_level_configuration(caplog: pytest.LogCaptureFixture) -> None:
    """Test that LOG_LEVEL is respected."""

    class DebugConfig(Config):
        LOG_LEVEL = logging.DEBUG

    with (
        caplog.at_level(logging.DEBUG),
        mock.patch("audiobook_automated.clients.manager.TorrentManager.verify_credentials", return_value=True),
    ):
        app = create_app(DebugConfig)
        assert app.logger.level == logging.DEBUG
