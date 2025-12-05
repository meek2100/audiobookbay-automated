# tests/unit/test_startup.py
import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import app
import app.app
import app.config


class MockConfig(dict):
    """
    A dictionary that behaves like a Flask config object (supporting from_object).
    """

    def from_object(self, obj):
        # Emulate Flask config.from_object by reading uppercase attributes
        for key in dir(obj):
            if key.isupper():
                self[key] = getattr(obj, key)


@pytest.fixture
def mock_flask_factory():
    """
    Patches Flask class to return a mock app with a traceable logger and working config.
    """
    with patch("flask.Flask") as mock_class:
        mock_app = MagicMock()
        mock_logger = MagicMock()
        mock_app.logger = mock_logger

        # Use a real dict-like object so it passes isinstance(config, dict)
        mock_config = MockConfig()
        mock_app.config = mock_config

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

    # Reload modules to restore original state
    with patch.dict(os.environ, safe_env):
        # FIX: Do not use sys.modules.pop(), it causes ImportError on reload.
        # Instead, assume dirty state and reload or re-import.
        importlib.reload(app.config)
        importlib.reload(app)

        # Reload app.app if it was loaded, otherwise import it
        if "app.app" in sys.modules:
            importlib.reload(sys.modules["app.app"])
        else:
            importlib.import_module("app.app")


def test_startup_missing_save_path(monkeypatch, mock_flask_factory):
    _, mock_logger = mock_flask_factory
    with patch("sys.exit") as mock_exit:
        monkeypatch.delenv("SAVE_PATH_BASE", raising=False)
        monkeypatch.delenv("TESTING", raising=False)

        # RELOAD ORDER IS CRITICAL:
        # 1. Reload config to read the new environment (missing SAVE_PATH_BASE)
        importlib.reload(app.config)
        # 2. Reload app package to update 'from .config import Config' reference
        importlib.reload(app)
        # 3. Reload app module to run create_app with the new Config
        if "app.app" in sys.modules:
            importlib.reload(sys.modules["app.app"])
        else:
            importlib.import_module("app.app")

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
            importlib.reload(app.config)
            importlib.reload(app)
            if "app.app" in sys.modules:
                importlib.reload(sys.modules["app.app"])
            else:
                importlib.import_module("app.app")

        assert "Application refused to start" in str(excinfo.value)
        args, _ = mock_logger.critical.call_args
        assert "CRITICAL SECURITY ERROR" in args[0]


def test_startup_insecure_secret_key_debug_warning(monkeypatch, mock_flask_factory):
    _, mock_logger = mock_flask_factory
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
    monkeypatch.setenv("SECRET_KEY", "change-this-to-a-secure-random-key")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.delenv("TESTING", raising=False)

    importlib.reload(app.config)
    importlib.reload(app)
    if "app.app" in sys.modules:
        importlib.reload(sys.modules["app.app"])
    else:
        importlib.import_module("app.app")

    args, _ = mock_logger.warning.call_args
    assert "WARNING: You are using the default insecure SECRET_KEY" in args[0]


def test_app_startup_verification_fail(monkeypatch, mock_flask_factory):
    """
    Test that verify_credentials is called during startup when not in testing mode.
    """
    _, mock_logger = mock_flask_factory
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
    try:
        # Patch the singleton instance in extensions
        with patch("app.extensions.torrent_manager.verify_credentials", return_value=False) as mock_verify:
            importlib.reload(app.config)
            importlib.reload(app)
            if "app.app" in sys.modules:
                importlib.reload(sys.modules["app.app"])
            else:
                importlib.import_module("app.app")

            # Assert that verification was attempted
            mock_verify.assert_called_once()
    finally:
        monkeypatch.setenv("TESTING", "1")
        importlib.reload(app.config)
        importlib.reload(app)
        if "app.app" in sys.modules:
            importlib.reload(sys.modules["app.app"])
        else:
            importlib.import_module("app.app")
