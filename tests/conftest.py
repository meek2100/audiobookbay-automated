import importlib
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def app_module():
    """
    Dynamically imports the app.app module.
    Crucial for tests that reload the module to change state.
    """
    if "app.app" not in sys.modules:
        return importlib.import_module("app.app")
    return sys.modules["app.app"]


@pytest.fixture(autouse=True)
def mock_torrent_clients(monkeypatch):
    """Globally mock the torrent client classes."""
    monkeypatch.setattr("app.clients.QbClient", MagicMock())
    monkeypatch.setattr("app.clients.TxClient", MagicMock())
    monkeypatch.setattr("app.clients.DelugeWebClient", MagicMock())


@pytest.fixture(autouse=True)
def _monkeypatch_response_class(request, monkeypatch):
    """
    Override pytest-flask's broken fixture.
    Prevents 'metaclass conflict' errors with Flask 3.x / Python 3.13.
    """
    pass


@pytest.fixture(autouse=True)
def reset_rate_limiter(app_module):
    """Reset the rate limiter before every test."""
    app_module.limiter.reset()


@pytest.fixture
def app(app_module):
    """Provides the Flask app instance from the current module."""
    flask_app = app_module.app
    flask_app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-key",
        }
    )
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()
