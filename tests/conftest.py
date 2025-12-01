from unittest.mock import MagicMock

import pytest

from app.app import app as flask_app


@pytest.fixture(autouse=True)
def mock_torrent_clients(monkeypatch):
    """
    Globally mock the torrent client classes to prevent accidental
    connections to real servers during tests.
    """
    monkeypatch.setattr("app.clients.QbClient", MagicMock())
    monkeypatch.setattr("app.clients.TxClient", MagicMock())
    monkeypatch.setattr("app.clients.DelugeWebClient", MagicMock())


@pytest.fixture
def app():
    flask_app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,  # Disable CSRF for easier API testing
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
