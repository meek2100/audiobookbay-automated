# tests/unit/test_config.py
"""Unit tests for configuration validation."""

import logging

import pytest
from pytest import LogCaptureFixture, MonkeyPatch

from audiobook_automated import config
from audiobook_automated.config import Config


def test_config_validate_success(monkeypatch: MonkeyPatch) -> None:
    """Ensure validation passes with valid configuration."""
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key")
    monkeypatch.setenv("SAVE_PATH_BASE", "/data")
    monkeypatch.setenv("DL_SCHEME", "https")
    # Patch class attributes as well since they are loaded at import
    monkeypatch.setattr(Config, "SECRET_KEY", "prod-secret-key")
    monkeypatch.setattr(Config, "SAVE_PATH_BASE", "/data")
    monkeypatch.setattr(Config, "DL_SCHEME", "https")
    monkeypatch.setattr(Config, "DL_CLIENT", "qbittorrent")  # Required now
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


def test_validate_dl_client_missing(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Test that Config.validate raises ValueError if DL_CLIENT is missing."""
    monkeypatch.setattr(Config, "DL_CLIENT", None)
    monkeypatch.setattr(Config, "SAVE_PATH_BASE", "/tmp")  # satisfy save path check
    monkeypatch.setattr(Config, "TESTING", False)

    with pytest.raises(ValueError) as exc:
        Config.validate(logging.getLogger("test"))

    assert "DL_CLIENT must be set" in str(exc.value)
    assert "Configuration Error: DL_CLIENT is missing" in caplog.text


def test_config_validate_insecure_secret_prod(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation raises ValueError for insecure secret key in production."""
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv("TESTING", "0")

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
    monkeypatch.setattr(Config, "LOG_LEVEL_STR", "INVALID_LEVEL")

    Config.validate(logging.getLogger("test"))

    assert "Configuration Warning: Invalid LOG_LEVEL 'INVALID_LEVEL' provided" in caplog.text


def test_config_validate_invalid_dl_scheme(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation fails for invalid DL_SCHEME."""
    monkeypatch.setattr(Config, "DL_SCHEME", "ftp")
    monkeypatch.setattr(Config, "DL_CLIENT", "qbittorrent")  # Satisfy prerequisite

    with pytest.raises(ValueError, match="Invalid DL_SCHEME"):
        Config.validate(logging.getLogger("test"))

    assert "Invalid DL_SCHEME" in caplog.text


def test_config_validate_page_limit_low(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation resets PAGE_LIMIT if < 1."""
    monkeypatch.setattr(Config, "PAGE_LIMIT", 0)
    monkeypatch.setattr(Config, "DL_CLIENT", "qbittorrent")  # Satisfy prerequisite

    Config.validate(logging.getLogger("test"))

    assert Config.PAGE_LIMIT == 3
    assert "Invalid PAGE_LIMIT '0'" in caplog.text


def test_parse_env_int_success(monkeypatch: MonkeyPatch) -> None:
    """Test parsing a valid integer string."""
    monkeypatch.setenv("TEST_INT", "42")
    assert config._parse_env_int("TEST_INT", 10) == 42


def test_parse_env_int_float_string(monkeypatch: MonkeyPatch) -> None:
    """Test parsing a float string as an integer (Docker/K8s common case)."""
    monkeypatch.setenv("TEST_INT", "42.0")
    assert config._parse_env_int("TEST_INT", 10) == 42


def test_parse_env_int_missing(monkeypatch: MonkeyPatch) -> None:
    """Test fallback to default when env var is missing."""
    monkeypatch.delenv("TEST_INT", raising=False)
    assert config._parse_env_int("TEST_INT", 10) == 10


def test_parse_env_int_invalid(monkeypatch: MonkeyPatch) -> None:
    """Test fallback to default when env var is invalid garbage."""
    monkeypatch.setenv("TEST_INT", "not-a-number")
    assert config._parse_env_int("TEST_INT", 10) == 10
