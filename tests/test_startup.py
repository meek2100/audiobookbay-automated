import importlib
import sys
from unittest.mock import patch

import pytest


def test_startup_missing_save_path(monkeypatch):
    """Test that the app exits with error if SAVE_PATH_BASE is missing."""
    with patch("sys.exit") as mock_exit:
        with patch("app.app.logger") as mock_logger:
            monkeypatch.delenv("SAVE_PATH_BASE", raising=False)
            monkeypatch.delenv("TESTING", raising=False)

            with patch("app.app.TorrentManager"):
                # FIX: Access the module from sys.modules to avoid getting the Flask instance
                importlib.reload(sys.modules["app.app"])

            mock_exit.assert_called_with(1)
            # Check for the specific error message in log calls
            args, _ = mock_logger.critical.call_args
            assert "Configuration Error: SAVE_PATH_BASE is missing" in args[0]


def test_startup_insecure_secret_key_production(monkeypatch):
    """Test that the app refuses to start in Production with default secret key."""
    with patch("sys.exit"):
        with patch("app.app.logger") as mock_logger:
            monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
            monkeypatch.setenv("SECRET_KEY", "change-this-to-a-secure-random-key")
            monkeypatch.setenv("FLASK_DEBUG", "0")
            monkeypatch.delenv("TESTING", raising=False)

            with pytest.raises(ValueError) as excinfo:
                with patch("app.app.TorrentManager"):
                    importlib.reload(sys.modules["app.app"])

            assert "Application refused to start" in str(excinfo.value)
            args, _ = mock_logger.critical.call_args
            assert "CRITICAL SECURITY ERROR" in args[0]


def test_startup_insecure_secret_key_debug_warning(monkeypatch):
    """Test that the app warns (but starts) in Debug mode with default secret key."""
    with patch("app.app.logger") as mock_logger:
        monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
        monkeypatch.setenv("SECRET_KEY", "change-this-to-a-secure-random-key")
        monkeypatch.setenv("FLASK_DEBUG", "1")
        monkeypatch.delenv("TESTING", raising=False)

        with patch("app.app.TorrentManager"):
            importlib.reload(sys.modules["app.app"])

        args, _ = mock_logger.warning.call_args
        assert "WARNING: You are using the default insecure SECRET_KEY" in args[0]
