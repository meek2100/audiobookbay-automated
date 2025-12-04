# tests/unit/test_startup.py
import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_flask_factory():
    """
    Patches Flask class to return a mock app with a traceable logger and working config.
    """
    with patch("flask.Flask") as mock_class:
        mock_app = MagicMock()
        mock_logger = MagicMock()
        mock_app.logger = mock_logger

        # HEIDEGGERIAN FIX: The config must 'be' a dictionary to function as a World
        # for extensions like flask-limiter.
        mock_config = {}
        mock_app.config = mock_config
        # Allow dictionary access on the mock object itself if accessed via attributes
        mock_app.config.__getitem__ = lambda k: mock_config[k]
        mock_app.config.__setitem__ = lambda k, v: mock_config.update({k: v})
        mock_app.config.get = mock_config.get

        mock_class.return_value = mock_app
        yield mock_class, mock_logger

    # --- TEARDOWN ---
    # Restore the app module to a clean state.
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
    _, mock_logger = mock_flask_factory
    with patch("sys.exit") as mock_exit:
        monkeypatch.delenv("SAVE_PATH_BASE", raising=False)
        monkeypatch.delenv("TESTING", raising=False)
        with patch("app.app.TorrentManager"):
            importlib.reload(sys.modules["app.app"])
        mock_exit.assert_called_with(1)
        args, _ = mock_logger.critical.call_args
        assert "Configuration Error: SAVE_PATH_BASE is missing" in args[0]


def test_startup_insecure_secret_key_production(monkeypatch, mock_flask_factory):
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
    _, mock_logger = mock_flask_factory
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
    try:
        with patch("app.clients.TorrentManager") as MockTM:
            MockTM.return_value.verify_credentials.return_value = False
            importlib.reload(sys.modules["app.app"])
            args, _ = mock_logger.warning.call_args
            assert "STARTUP WARNING: Torrent client is unreachable" in args[0]
    finally:
        monkeypatch.setenv("TESTING", "1")
        importlib.reload(sys.modules["app.app"])
