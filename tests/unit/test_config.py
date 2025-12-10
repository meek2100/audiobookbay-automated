"""Unit tests for configuration validation."""

import importlib
import logging

import pytest
from pytest import LogCaptureFixture, MonkeyPatch

from app import config
from app.config import Config


def test_config_validate_success(monkeypatch: MonkeyPatch) -> None:
    """Ensure validation passes with valid configuration."""
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key")
    monkeypatch.setenv("SAVE_PATH_BASE", "/data")
    monkeypatch.setenv("DL_SCHEME", "https")
    # Patch class attributes as well since they are loaded at import
    monkeypatch.setattr(Config, "SECRET_KEY", "prod-secret-key")
    monkeypatch.setattr(Config, "SAVE_PATH_BASE", "/data")
    monkeypatch.setattr(Config, "DL_SCHEME", "https")
    monkeypatch.setattr(Config, "TESTING", False)
    monkeypatch.setattr(Config, "FLASK_DEBUG", False)

    # Should not raise
    Config.validate(logging.getLogger("test"))


def test_config_validate_missing_save_path(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation fails hard if SAVE_PATH_BASE is missing."""
    monkeypatch.setenv("SAVE_PATH_BASE", "")
    monkeypatch.setattr(Config, "SAVE_PATH_BASE", None)
    # Force TESTING to False to trigger the validation error
    monkeypatch.setattr(Config, "TESTING", False)

    with pytest.raises(RuntimeError):
        Config.validate(logging.getLogger("test"))

    assert "Configuration Error: SAVE_PATH_BASE is missing" in caplog.text


def test_config_validate_insecure_secret_prod(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation raises ValueError for insecure secret key in production."""
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv("TESTING", "0")

    # Use setattr to prevent polluting the Config class for other tests
    monkeypatch.setattr(Config, "FLASK_DEBUG", False)
    monkeypatch.setattr(Config, "TESTING", False)
    monkeypatch.setattr(Config, "SECRET_KEY", "change-this-to-a-secure-random-key")

    with pytest.raises(ValueError, match="Application refused to start"):
        Config.validate(logging.getLogger("test"))

    assert "CRITICAL SECURITY ERROR" in caplog.text


def test_config_validate_insecure_secret_dev(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation only warns for insecure secret key in dev/test."""
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.setattr(Config, "FLASK_DEBUG", True)
    monkeypatch.setattr(Config, "SECRET_KEY", "change-this-to-a-secure-random-key")

    # Should not raise
    Config.validate(logging.getLogger("test"))

    assert "WARNING: You are using the default insecure SECRET_KEY" in caplog.text


def test_config_validate_invalid_log_level(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation warns on invalid LOG_LEVEL and defaults to INFO."""
    monkeypatch.setenv("LOG_LEVEL", "INVALID_LEVEL")
    # We must patch the class attribute because it's loaded at import time
    monkeypatch.setattr(Config, "LOG_LEVEL_STR", "INVALID_LEVEL")

    Config.validate(logging.getLogger("test"))

    assert "Configuration Warning: Invalid LOG_LEVEL 'INVALID_LEVEL' provided" in caplog.text


def test_config_validate_invalid_dl_scheme(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation fails for invalid DL_SCHEME."""
    monkeypatch.setattr(Config, "DL_SCHEME", "ftp")

    with pytest.raises(ValueError, match="Invalid DL_SCHEME"):
        Config.validate(logging.getLogger("test"))

    assert "Invalid DL_SCHEME" in caplog.text


def test_config_validate_page_limit_low(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation resets PAGE_LIMIT if < 1."""
    monkeypatch.setattr(Config, "PAGE_LIMIT", 0)

    Config.validate(logging.getLogger("test"))

    assert Config.PAGE_LIMIT == 3
    assert "Invalid PAGE_LIMIT '0'" in caplog.text


def test_config_page_limit_parsing_error(monkeypatch: MonkeyPatch) -> None:
    """Ensure module-level parsing falls back to 3 on invalid int."""
    monkeypatch.setenv("PAGE_LIMIT", "not_an_integer")

    # Reload the module to re-execute the module-level parsing logic
    importlib.reload(config)

    assert config.Config.PAGE_LIMIT == 3


def test_config_scraper_threads_parsing_error(monkeypatch: MonkeyPatch) -> None:
    """Ensure module-level parsing falls back to 3 on invalid SCRAPER_THREADS."""
    monkeypatch.setenv("SCRAPER_THREADS", "invalid_int")

    # Reload to re-trigger parsing
    importlib.reload(config)

    assert config.Config.SCRAPER_THREADS == 3


def test_config_scraper_timeout_parsing_error(monkeypatch: MonkeyPatch) -> None:
    """Ensure module-level parsing falls back to 30 on invalid SCRAPER_TIMEOUT.

    Covers app/config.py lines 83-84 (ValueError block).
    """
    monkeypatch.setenv("SCRAPER_TIMEOUT", "invalid_int")

    # Reload to re-trigger parsing
    importlib.reload(config)

    assert config.Config.SCRAPER_TIMEOUT == 30
