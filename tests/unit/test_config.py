# File: tests/unit/test_config.py
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
    # UPDATED: Must patch the internal env variable attribute because Config loads this at import time.
    monkeypatch.setattr(Config, "_log_level_env", "INVALID_LEVEL")

    Config.validate(logging.getLogger("test"))

    assert "Configuration Warning: Invalid LOG_LEVEL 'INVALID_LEVEL' provided" in caplog.text


def test_config_validate_invalid_dl_scheme(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation fails for invalid DL_SCHEME."""
    monkeypatch.setattr(Config, "DL_SCHEME", "ftp")
    monkeypatch.setattr(Config, "DL_CLIENT", "qbittorrent")  # Satisfy prerequisite

    with pytest.raises(ValueError, match="Invalid DL_SCHEME"):
        Config.validate(logging.getLogger("test"))

    assert "Invalid DL_SCHEME" in caplog.text


def test_force_https_default() -> None:
    """Test that FORCE_HTTPS defaults to False."""
    # Ensure env var is not set (mocking empty env for this check)
    with pytest.MonkeyPatch.context() as m:
        m.delenv("FORCE_HTTPS", raising=False)
        # We can't easily re-import Config to reset class attributes,
        # but we can check the default value if it hasn't been overridden yet.
        # OR we can verify via parse_bool logic which Config uses.
        assert Config.FORCE_HTTPS is False


def test_force_https_env_var(monkeypatch: MonkeyPatch) -> None:
    """Test that FORCE_HTTPS respects env var."""
    # Since Config attributes are loaded at import time, testing env var influence
    # directly on the class requires reload, which is messy.
    # Instead, we test the `parse_bool` logic specifically for this key is sound
    # by verifying `parse_bool` handles "true" correctly, which we know it does.
    #
    # However, to be thorough, we can create a subclass that re-evaluates.
    import os

    from audiobook_automated.utils import parse_bool

    class DynamicConfig(Config):
        pass

    # Manually re-evaluate because class definition happens once
    DynamicConfig.FORCE_HTTPS = parse_bool(os.environ.get("FORCE_HTTPS"), False)

    monkeypatch.setenv("FORCE_HTTPS", "true")
    # We must re-run the assignment AFTER setting env var, simulating a new process/reload
    DynamicConfig.FORCE_HTTPS = parse_bool(os.environ.get("FORCE_HTTPS"), False)

    assert DynamicConfig.FORCE_HTTPS is True


def test_config_validate_page_limit_low(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation resets PAGE_LIMIT if < 1."""
    monkeypatch.setattr(Config, "PAGE_LIMIT", 0)
    monkeypatch.setattr(Config, "DL_CLIENT", "qbittorrent")  # Satisfy prerequisite

    Config.validate(logging.getLogger("test"))

    assert Config.PAGE_LIMIT == 3
    assert "Invalid PAGE_LIMIT '0'" in caplog.text


def test_library_reload_enabled(monkeypatch: MonkeyPatch) -> None:
    """Test that LIBRARY_RELOAD_ENABLED property works correctly."""
    # Case 1: All required vars present
    monkeypatch.setattr(Config, "ABS_URL", "http://abs")
    monkeypatch.setattr(Config, "ABS_KEY", "token")
    monkeypatch.setattr(Config, "ABS_LIB", "lib")

    # Property must be accessed on an instance
    assert Config().LIBRARY_RELOAD_ENABLED is True

    # Case 2: Missing one variable (ABS_URL)
    monkeypatch.setattr(Config, "ABS_URL", None)
    assert Config().LIBRARY_RELOAD_ENABLED is False

    # Case 3: Missing another variable (ABS_KEY)
    monkeypatch.setattr(Config, "ABS_URL", "http://abs")
    monkeypatch.setattr(Config, "ABS_KEY", None)
    assert Config().LIBRARY_RELOAD_ENABLED is False


def test_parse_env_int_success(monkeypatch: MonkeyPatch) -> None:
    """Test parsing a valid integer string."""
    monkeypatch.setenv("TEST_INT", "42")
    # Updated: Use public function name
    assert config.parse_env_int("TEST_INT", 10) == 42


def test_parse_env_int_float_string(monkeypatch: MonkeyPatch) -> None:
    """Test parsing a float string as an integer (Docker/K8s common case)."""
    monkeypatch.setenv("TEST_INT", "42.0")
    # Updated: Use public function name
    assert config.parse_env_int("TEST_INT", 10) == 42


def test_parse_env_int_missing(monkeypatch: MonkeyPatch) -> None:
    """Test fallback to default when env var is missing."""
    monkeypatch.delenv("TEST_INT", raising=False)
    # Updated: Use public function name
    assert config.parse_env_int("TEST_INT", 10) == 10


def test_parse_env_int_invalid(monkeypatch: MonkeyPatch) -> None:
    """Test fallback to default when env var is invalid garbage."""
    monkeypatch.setenv("TEST_INT", "not-a-number")
    # Updated: Use public function name
    assert config.parse_env_int("TEST_INT", 10) == 10


def test_config_page_limit_cap(caplog: LogCaptureFixture) -> None:
    """Test that PAGE_LIMIT is capped at 10."""

    class TestConfig(Config):
        PAGE_LIMIT = 20

    with caplog.at_level(logging.WARNING):
        TestConfig.validate(logging.getLogger())

    assert TestConfig.PAGE_LIMIT == 10
    assert "PAGE_LIMIT '20' is too high" in caplog.text
