"""Unit tests for configuration validation."""

import logging

import pytest
from pytest import LogCaptureFixture, MonkeyPatch

from app.config import Config


def test_config_validate_missing_save_path(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation fails hard if SAVE_PATH_BASE is missing."""
    monkeypatch.setenv("SAVE_PATH_BASE", "")
    Config.SAVE_PATH_BASE = None

    with pytest.raises(SystemExit):
        Config.validate(logging.getLogger("test"))

    assert "Configuration Error: SAVE_PATH_BASE is missing" in caplog.text


def test_config_validate_insecure_secret_prod(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation raises ValueError for insecure secret key in production."""
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv("TESTING", "0")
    Config.FLASK_DEBUG = False
    Config.TESTING = False
    Config.SECRET_KEY = "change-this-to-a-secure-random-key"

    with pytest.raises(ValueError, match="Application refused to start"):
        Config.validate(logging.getLogger("test"))

    assert "CRITICAL SECURITY ERROR" in caplog.text


def test_config_validate_insecure_secret_dev(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    """Ensure validation only warns for insecure secret key in dev/test."""
    monkeypatch.setenv("FLASK_DEBUG", "1")
    Config.FLASK_DEBUG = True
    Config.SECRET_KEY = "change-this-to-a-secure-random-key"

    # Should not raise
    Config.validate(logging.getLogger("test"))

    assert "WARNING: You are using the default insecure SECRET_KEY" in caplog.text
