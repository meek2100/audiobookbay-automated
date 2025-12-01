import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_flask_factory():
    """Patches Flask class to return a mock app with a traceable logger and working config."""
    with patch("flask.Flask") as mock_class:
        mock_app = MagicMock()
        mock_logger = MagicMock()
        mock_app.logger = mock_logger
        # FIX: config must be a real dict so flask-limiter gets real values (not Mocks)
        mock_app.config = {}
        mock_class.return_value = mock_app
        yield mock_class, mock_logger


def test_startup_missing_save_path(monkeypatch, mock_flask_factory):
    """Test that the app exits with error if SAVE_PATH_BASE is missing."""
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
