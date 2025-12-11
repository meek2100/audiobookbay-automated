# tests/conftest.py
from __future__ import annotations

from typing import Any, Generator, cast

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


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create the 'World' for the tests: A Flask application instance.

    Uses TestConfig to ensure configuration is present before extension initialization.
    """
    app = create_app(TestConfig)

    yield app


@pytest.fixture
def client(app: Flask) -> FlaskClient[Any]:
    """The observer within the world: A test client to make requests."""
    return app.test_client()


@pytest.fixture
def runner(app: Flask) -> FlaskCliRunner:
    """A CLI runner for command-line context."""
    return cast(FlaskCliRunner, app.test_cli_runner())


@pytest.fixture(autouse=True)
def push_app_context(app: Flask) -> Generator[None, None, None]:
    """Automatically push application context for all tests."""
    with app.app_context():
        yield
