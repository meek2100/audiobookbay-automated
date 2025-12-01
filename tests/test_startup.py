import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_flask_factory():
    """
    Patches Flask class to return a mock app with a traceable logger and working config.
    CRITICAL: Automatically restores the real app module after the test to prevent
    pollution of the global namespace for subsequent tests.
    """
    with patch("flask.Flask") as mock_class:
        mock_app = MagicMock()
        mock_logger = MagicMock()
        mock_app.logger = mock_logger
        # FIX: config must be a real dict so flask-limiter gets real values (not Mocks)
        mock_app.config = {}
        mock_class.return_value = mock_app
        yield mock_class, mock_logger

    # --- TEARDOWN ---
    # Restore the app module to a clean state.
    # CRITICAL FIX: We must force a "Safe Mode" environment during this reload.
    # Otherwise, if a test deleted SAVE_PATH_BASE or unset TESTING, the reload
    # itself will crash with SystemExit or ValueError, failing the test suite.
    safe_env = {
        "TESTING": "1",
        "SAVE_PATH_BASE": "/tmp/startup_test_safe_restore",
        "SECRET_KEY": "startup_test_safe_key",
        "FLASK_DEBUG": "0",
    }

    if "app.app" in sys.modules:
        with patch.dict(os.environ, safe_env):
            importlib.reload(sys.modules["app.app"])


def test_startup_missing_save_path(monkeypatch, mock_flask_factory):
    """Test that the app exits with error if SAVE_PATH_BASE is missing."""
    _, mock_logger = mock_flask_factory

    with patch("sys.exit") as mock_exit:
        monkeypatch.delenv("SAVE_PATH_BASE", raising=False)
        monkeypatch.delenv("TESTING", raising=False)

        # Patch TorrentManager to prevent it from trying to connect during import
        with patch("app.app.TorrentManager"):
            importlib.reload(sys.modules["app.app"])

        mock_exit.assert_called_with(1)
        args, _ = mock_logger.critical.call_args
        assert "Configuration Error: SAVE_PATH_BASE is missing" in args[0]


def test_startup_insecure_secret_key_production(monkeypatch, mock_flask_factory):
    """Test that the app refuses to start in Production with default secret key."""
    _, mock_logger = mock_flask_factory

    with patch("sys.exit"):
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


def test_startup_insecure_secret_key_debug_warning(monkeypatch, mock_flask_factory):
    """Test that the app warns (but starts) in Debug mode with default secret key."""
    _, mock_logger = mock_flask_factory

    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
    monkeypatch.setenv("SECRET_KEY", "change-this-to-a-secure-random-key")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.delenv("TESTING", raising=False)

    with patch("app.app.TorrentManager"):
        importlib.reload(sys.modules["app.app"])

    args, _ = mock_logger.warning.call_args
    assert "WARNING: You are using the default insecure SECRET_KEY" in args[0]


def test_app_startup_verification_fail(monkeypatch, mock_flask_factory):
    """Test that app handles verify_credentials failure gracefully at startup."""
    _, mock_logger = mock_flask_factory

    # 1. SETUP: Simulate Production Env to trigger verification
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")

    try:
        # Patch the client where it is imported in app.app
        with patch("app.clients.TorrentManager") as MockTM:
            MockTM.return_value.verify_credentials.side_effect = Exception("Auth Bad")

            # 2. ACTION: Reload to run top-level startup logic
            importlib.reload(sys.modules["app.app"])

            # 3. ASSERT: Check logs
            args, _ = mock_logger.error.call_args
            assert "STARTUP WARNING" in args[0]
            assert "Auth Bad" in str(args[0])
    finally:
        # 4. TEARDOWN: Restore app to Testing mode explicitly
        # (Though the fixture teardown now handles this safely too)
        monkeypatch.setenv("TESTING", "1")
        importlib.reload(sys.modules["app.app"])
