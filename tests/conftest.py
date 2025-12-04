# tests/conftest.py
import pytest

from app import create_app


@pytest.fixture
def app():
    """
    Creates the 'World' for the tests: A Flask application instance
    configured specifically for testing (safe paths, disabled CSRF).
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


@pytest.fixture
def client(app):
    """
    The observer within the world: A test client to make requests.
    """
    return app.test_client()


@pytest.fixture
def runner(app):
    """
    A CLI runner for command-line context.
    """
    return app.test_cli_runner()
