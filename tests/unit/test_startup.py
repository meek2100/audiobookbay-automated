# tests/unit/test_startup.py
"""Unit tests for startup configuration and verification logic."""

import importlib
import os
import sys
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import pytest

import audiobook_automated
import audiobook_automated.app
import audiobook_automated.config


class MockConfig(dict[str, Any]):
    """A dictionary that behaves like a Flask config object (supporting from_object)."""

    def from_object(self, obj: Any) -> None:
        """Emulate Flask config.from_object by reading uppercase attributes."""
        for key in dir(obj):
            if key.isupper():
                self[key] = getattr(obj, key)


@pytest.fixture
def mock_flask_factory() -> Generator[tuple[Any, Any]]:
    """Patch Flask class to return a mock app with a traceable logger and working config."""
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
    # Restore the app module to a clean state to prevent pollution between tests.
    safe_env = {
        "TESTING": "1",
        "SAVE_PATH_BASE": "/tmp/startup_test_safe_restore",
        "SECRET_KEY": "startup_test_safe_key",
        "FLASK_DEBUG": "0",
        "LOG_LEVEL": "INFO",
    }

    # Reload modules to restore original state
    with patch.dict(os.environ, safe_env):
        # Do not use sys.modules.pop(), it causes ImportError on reload.
        importlib.reload(audiobook_automated.config)
        importlib.reload(audiobook_automated)

        if "audiobook_automated.app" in sys.modules:
            importlib.reload(sys.modules["audiobook_automated.app"])
        else:
            importlib.import_module("audiobook_automated.app")


def test_startup_missing_save_path(monkeypatch: Any, mock_flask_factory: Any) -> None:
    """Ensure startup fails with critical error if SAVE_PATH_BASE is missing."""
    _, mock_logger = mock_flask_factory

    # Updated: Expect RuntimeError instead of SystemExit (Gunicorn safety improvement)
    monkeypatch.delenv("SAVE_PATH_BASE", raising=False)
    monkeypatch.delenv("TESTING", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        importlib.reload(audiobook_automated.config)
        importlib.reload(audiobook_automated)
        if "audiobook_automated.app" in sys.modules:
            importlib.reload(sys.modules["audiobook_automated.app"])
        else:
            importlib.import_module("audiobook_automated.app")

    assert "Configuration Error: SAVE_PATH_BASE is missing" in str(excinfo.value)
    args, _ = mock_logger.critical.call_args
    assert "Configuration Error: SAVE_PATH_BASE is missing" in args[0]


def test_startup_insecure_secret_key_production(monkeypatch: Any, mock_flask_factory: Any) -> None:
    """Ensure startup raises ValueError for insecure secret key in production."""
    _, mock_logger = mock_flask_factory

    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
    monkeypatch.setenv("SECRET_KEY", "change-this-to-a-secure-random-key")
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.delenv("TESTING", raising=False)

    with pytest.raises(ValueError) as excinfo:
        importlib.reload(audiobook_automated.config)
        importlib.reload(audiobook_automated)
        if "audiobook_automated.app" in sys.modules:
            importlib.reload(sys.modules["audiobook_automated.app"])
        else:
            importlib.import_module("audiobook_automated.app")

    assert "Application refused to start" in str(excinfo.value)
    args, _ = mock_logger.critical.call_args
    assert "CRITICAL SECURITY ERROR" in args[0]


def test_startup_invalid_page_limit(monkeypatch: Any, mock_flask_factory: Any) -> None:
    """Test that invalid PAGE_LIMIT (<= 0) is reset to default."""
    _, mock_logger = mock_flask_factory
    monkeypatch.setenv("PAGE_LIMIT", "-5")
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")

    importlib.reload(audiobook_automated.config)
    # Validate manually as we are testing config logic specifically
    audiobook_automated.config.Config.validate(mock_logger)

    assert audiobook_automated.config.Config.PAGE_LIMIT == 3
    args, _ = mock_logger.warning.call_args
    assert "Invalid PAGE_LIMIT" in args[0]


def test_startup_invalid_page_limit_type(monkeypatch: Any, mock_flask_factory: Any) -> None:
    """Test that non-integer PAGE_LIMIT defaults to 3."""
    _, mock_logger = mock_flask_factory
    monkeypatch.setenv("PAGE_LIMIT", "invalid_string")
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")

    importlib.reload(audiobook_automated.config)
    # The parsing logic happens at import time for PAGE_LIMIT.
    assert audiobook_automated.config.Config.PAGE_LIMIT == 3


def test_startup_insecure_secret_key_development(monkeypatch: Any, mock_flask_factory: Any) -> None:
    """Ensure startup only warns for insecure secret key in dev/test."""
    _, mock_logger = mock_flask_factory
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
    monkeypatch.setenv("SECRET_KEY", "change-this-to-a-secure-random-key")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.delenv("TESTING", raising=False)

    importlib.reload(audiobook_automated.config)
    audiobook_automated.config.Config.validate(mock_logger)

    args, _ = mock_logger.warning.call_args
    assert "WARNING: You are using the default insecure SECRET_KEY" in args[0]


def test_startup_invalid_log_level(monkeypatch: Any, mock_flask_factory: Any) -> None:
    """Ensure startup warns on invalid LOG_LEVEL."""
    _, mock_logger = mock_flask_factory
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
    monkeypatch.setenv("LOG_LEVEL", "INVALID_LEVEL")

    importlib.reload(audiobook_automated.config)
    audiobook_automated.config.Config.validate(mock_logger)

    args, _ = mock_logger.warning.call_args
    assert "Configuration Warning: Invalid LOG_LEVEL" in args[0]


def test_create_app_uses_version_file(monkeypatch: Any, mock_flask_factory: Any) -> None:
    """Test that create_app reads STATIC_VERSION from version.txt if present (Optimization)."""
    mock_class, _ = mock_flask_factory

    # CRITICAL: Reload app module so it imports the patched Flask class from the fixture.
    # Without this, app.create_app() uses the real Flask class, causing the mock assertions to fail.
    importlib.reload(audiobook_automated)

    mock_app = mock_class.return_value
    mock_app.root_path = "/mock/root"

    # Ensure environment is valid for create_app
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp/test")

    expected_hash = "production-hash-123"

    with (
        patch("audiobook_automated.os.path.exists") as mock_exists,
        patch("builtins.open", mock_open(read_data=expected_hash)) as mock_file,
        patch("audiobook_automated.calculate_static_hash") as mock_calc,
    ):
        # Configure exists to return True only if checking for version.txt
        mock_exists.side_effect = lambda p: p.endswith("version.txt")

        # Call create_app directly
        audiobook_automated.create_app()

        assert mock_app.config["STATIC_VERSION"] == expected_hash

        mock_file.assert_called_once()
        args, _ = mock_file.call_args
        assert args[0].endswith("version.txt")

        # Verify the expensive calculation was skipped
        mock_calc.assert_not_called()
