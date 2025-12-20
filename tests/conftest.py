# File: tests/conftest.py
"""Global pytest fixtures and configuration for the test suite.

This module defines the 'World' in which tests run, including the Flask application
instance, test clients, and global configuration overrides (like disabling CSRF
for API tests).
"""

from __future__ import annotations

from collections.abc import Generator
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
    SAVE_PATH_BASE = "/tmp/test_downloads"
    SECRET_KEY = "test-secret-key"
    WTF_CSRF_ENABLED = False

    # Enable Rate Limit headers for assertions
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_ENABLED = True

    # Prevent real connections in config
    DL_HOST = "mock_localhost"


@pytest.fixture(autouse=True)
def mock_global_dependencies() -> Generator[None]:
    """Isolate the test suite from the real world.

    This fixture runs automatically for every test. It mocks the heavy
    lifters (TorrentManager) to prevent the application from trying to
    connect to a real torrent client during startup or request handling,
    which is likely the cause of local live connection errors.
    """
    # We patch where it is USED in the routes/app
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        # Configure the mock to behave 'normally' so tests that don't customize it still pass
        mock_tm.get_status.return_value = []
        mock_tm.add_magnet.return_value = "OK"
        yield


@pytest.fixture
def app() -> Generator[Flask]:
    """Create the 'World' for the tests: A Flask application instance.

    Uses TestConfig to ensure configuration is present before extension initialization.
    """
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
