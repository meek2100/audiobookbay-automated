# tests/conftest.py
from typing import Any, Generator

import pytest
from flask import Flask
from flask.testing import FlaskClient, FlaskCliRunner

from app import create_app


@pytest.fixture  # type: ignore[untyped-decorator]
def app() -> Generator[Flask, None, None]:
    """Create the 'World' for the tests: A Flask application instance.

    Configured specifically for testing (safe paths, disabled CSRF).
    """
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "SAVE_PATH_BASE": "/tmp/test_downloads",
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,  # Disable CSRF for easier functional testing
        }
    )

    yield app


@pytest.fixture  # type: ignore[untyped-decorator]
def client(app: Flask) -> FlaskClient[Any]:
    """The observer within the world: A test client to make requests."""
    return app.test_client()


@pytest.fixture  # type: ignore[untyped-decorator]
def runner(app: Flask) -> FlaskCliRunner:
    """A CLI runner for command-line context."""
    return app.test_cli_runner()
