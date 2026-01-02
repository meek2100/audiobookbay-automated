# File: tests/conftest.py
"""Global pytest fixtures and configuration for the test suite.

This module defines the 'World' in which tests run, including the Flask application
instance, test clients, and global configuration overrides.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient, FlaskCliRunner

from audiobook_automated import create_app
from audiobook_automated.config import Config


class TestConfig(Config):
    """Test configuration with overrides.

    Passed to create_app to ensure extensions (like Flask-Limiter)
    pick up settings during their init_app() phase.
    """

    TESTING = True
    # CROSS-PLATFORM FIX: Use system temp directory instead of hardcoded /tmp
    # This prevents permission issues or creation of C:\tmp on Windows.
    SAVE_PATH_BASE = os.path.join(tempfile.gettempdir(), "test_downloads")
    SECRET_KEY = "test-secret-key"
    WTF_CSRF_ENABLED = False

    # Enable Rate Limit headers for assertions
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_ENABLED = True

    # Prevent real connections in config
    DL_HOST = "mock_localhost"


@pytest.fixture(autouse=True)
def mock_sleep() -> Generator[Any]:
    """Globally mock time.sleep for ALL tests to speed up execution.

    Moved here from tests/scraper/conftest.py to ensure Functional and Unit
    tests also benefit from zero-delay sleeps (e.g. when testing search routes).
    """
    with patch("time.sleep") as mock_sleep:
        yield mock_sleep


@pytest.fixture
def app() -> Generator[Flask]:
    """Create the 'World' for the tests: A Flask application instance.

    Uses TestConfig to ensure configuration is present before extension initialization.
    """
    # CRITICAL FIX: Patch verify_credentials ONLY during creation.
    # This bypasses the startup connection check (init_app) so creating the app is safe.
    # We use a context manager so the patch is removed after create_app returns.
    # This allows unit tests (which rely on this app fixture) to subsequently test
    # the REAL TorrentManager logic without being globally mocked.
    with patch("audiobook_automated.clients.manager.TorrentManager.verify_credentials", return_value=True):
        app = create_app(TestConfig)

    yield app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """The observer within the world: A test client to make requests."""
    return app.test_client()


@pytest.fixture
def runner(app: Flask) -> FlaskCliRunner:
    """A CLI runner for command-line context."""
    return app.test_cli_runner()


@pytest.fixture(autouse=True)
def push_app_context(app: Flask) -> Generator[None]:
    """Automatically push application context for all tests."""
    with app.app_context():
        yield
