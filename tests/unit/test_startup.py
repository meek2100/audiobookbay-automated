# File: tests/unit/test_startup.py
"""Unit tests for startup configuration and verification logic."""

import importlib
import logging
import os
import sys
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import pytest

import audiobook_automated
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
    # FIX: Use underscore for unused variables to satisfy pyright 'reportUnusedVariable'
    _ = mock_flask_factory
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
        # FIX: Patch torrent_manager to prevent real connection attempt during startup
        patch("audiobook_automated.torrent_manager") as mock_torrent_manager,
    ):
        # Configure exists to return True only if checking for version.txt
        # FIX: Explicitly type lambda parameter or use inner function to avoid pyright unknown type error
        def side_effect(p: str | Any) -> bool:
            return str(p).endswith("version.txt")

        mock_exists.side_effect = side_effect

        # Mock the verify_credentials return to avoid warnings
        mock_torrent_manager.verify_credentials.return_value = True

        # Call create_app directly
        audiobook_automated.create_app()

        assert mock_app.config["STATIC_VERSION"] == expected_hash

        mock_file.assert_called_once()
        args, _ = mock_file.call_args
        assert args[0].endswith("version.txt")

        # Verify the expensive calculation was skipped
        mock_calc.assert_not_called()


def test_app_entry_point() -> None:
    """Ensures the app module can be imported and the global app instance is created.

    Reloading ensures coverage captures the top-level code execution.
    """
    # FIX: Use sys.modules to retrieve the actual module object.
    # We assign the result to 'reloaded_module' to ensure we are asserting
    # on the module itself, not the 'app' variable inside the 'app' package.
    # Check if loaded, if not import it
    if "audiobook_automated.app" not in sys.modules:
        importlib.import_module("audiobook_automated.app")

    reloaded_module = importlib.reload(sys.modules["audiobook_automated.app"])

    # Verify that the module contains the 'app' variable (the Flask instance)
    assert reloaded_module.app is not None


def test_create_app_with_gunicorn_integration(monkeypatch: Any, mock_flask_factory: Any) -> None:
    """Test that Gunicorn logger handlers are attached if present."""
    _, mock_app_logger = mock_flask_factory

    # Simulate environment where Config.LOG_LEVEL is NOT set/detected
    # We must patch config BEFORE reload so the class defaults are correct
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
    # Set to empty to trigger fallback logic
    monkeypatch.setenv("LOG_LEVEL", "")

    # We must patch getLogger to simulate Gunicorn environment
    mock_gunicorn_logger = MagicMock()
    # Use MagicMock objects for handlers to satisfy MyPy (list[Handler] vs list[str])
    mock_handler = MagicMock()
    mock_gunicorn_logger.handlers = [mock_handler]
    mock_gunicorn_logger.level = 20  # INFO

    original_get_logger = logging.getLogger

    def side_effect(name: str) -> Any:
        if name == "gunicorn.error":
            return mock_gunicorn_logger
        return original_get_logger(name)

    # Reload to apply env vars to Config
    importlib.reload(audiobook_automated.config)
    importlib.reload(audiobook_automated)

    with patch("logging.getLogger", side_effect=side_effect):
        with patch("audiobook_automated.torrent_manager"):  # Silence connection warning
            app = audiobook_automated.create_app()

            # Verify handlers were attached
            # Use mock objects to ensure type compatibility
            assert app.logger.handlers == [mock_handler]
            # Verify that due to missing LOG_LEVEL, we fell back to Gunicorn's level
            # Use the mock_app_logger directly to avoid MyPy errors on the Flask app.logger type
            mock_app_logger.setLevel.assert_called_with(20)


def test_create_app_with_gunicorn_and_config_override(monkeypatch: Any, mock_flask_factory: Any) -> None:
    """Test that Config LOG_LEVEL overrides Gunicorn level if set."""
    _, mock_app_logger = mock_flask_factory

    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")
    # User explicit override (10 = DEBUG)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    mock_gunicorn_logger = MagicMock()
    # Ensure handlers exist so we enter the 'if gunicorn_logger.handlers:' block
    mock_gunicorn_logger.handlers = [MagicMock()]
    mock_gunicorn_logger.level = 40  # ERROR

    original_get_logger = logging.getLogger

    def side_effect(name: str) -> Any:
        if name == "gunicorn.error":
            return mock_gunicorn_logger
        return original_get_logger(name)

    # Reload to apply env vars to Config
    importlib.reload(audiobook_automated.config)
    importlib.reload(audiobook_automated)

    with patch("logging.getLogger", side_effect=side_effect):
        with patch("audiobook_automated.torrent_manager"):
            # FIX: Do not assign to unused variable 'app'
            audiobook_automated.create_app()

            # Should use DEBUG (10) from config, ignoring Gunicorn's ERROR (40)
            mock_app_logger.setLevel.assert_called_with(10)
