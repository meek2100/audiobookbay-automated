# File: tests/unit/test_startup.py
"""Unit tests for application startup logic."""

from unittest.mock import patch

from audiobook_automated import create_app
from audiobook_automated.config import Config


class StartupConfig(Config):
    """Configuration for startup tests."""

    TESTING = True
    DL_CLIENT = "qbittorrent"


def test_startup_connection_warning(caplog) -> None:
    """Test that a warning is logged if the torrent client is unreachable at startup.

    This covers the `if not torrent_manager.verify_credentials():` block in __init__.py.
    """
    # We patch verify_credentials directly on the global instance
    # because create_app uses the global instance.
    from audiobook_automated.extensions import torrent_manager

    with patch.object(torrent_manager, "verify_credentials", return_value=False):
        # We also need to patch init_app to prevent it from trying to load plugins if we don't want to test that here
        # But we do want init_app to run to set up the client_type, so we assume it works or mock it?
        # If we use StartupConfig with DL_CLIENT, init_app will try to load plugin.
        # We should probably mock init_app to do nothing, but verify_credentials depends on it?
        # verify_credentials calls _get_strategy.
        # It's simpler to just force verify_credentials to False.

        create_app(StartupConfig)

        # Assert the warning was logged
        assert "Startup Check: Torrent client is NOT connected" in caplog.text


def test_startup_connection_success(caplog) -> None:
    """Test that no warning is logged if the torrent client connects."""
    from audiobook_automated.extensions import torrent_manager

    with patch.object(torrent_manager, "verify_credentials", return_value=True):
        create_app(StartupConfig)

        # Assert the warning was NOT logged
        assert "Startup Check: Torrent client is NOT connected" not in caplog.text
