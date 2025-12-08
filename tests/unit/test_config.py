"""Unit tests for configuration validation."""

import logging

import pytest
from pytest import LogCaptureFixture, MonkeyPatch

from app.config import Config


def test_config_validate_missing_save_path(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation fails hard if SAVE_PATH_BASE is missing."""
    monkeypatch.setenv("SAVE_PATH_BASE", "")
    monkeypatch.setattr(Config, "SAVE_PATH_BASE", None)
    # Force TESTING to False to trigger the sys.exit(1) call
    monkeypatch.setattr(Config, "TESTING", False)

    with pytest.raises(SystemExit):
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
