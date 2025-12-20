"""Shared fixtures for client tests."""

from collections.abc import Generator
from typing import Any

import pytest
from flask import Flask

from audiobook_automated.clients import TorrentManager


@pytest.fixture
def app() -> Generator[Flask]:
    """Create a minimal Flask app for testing context."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    # Default configs that can be overridden by monkeypatch/direct assignment
    app.config["DL_CLIENT"] = "qbittorrent"
    app.config["DL_HOST"] = "localhost"
    app.config["DL_PORT"] = "8080"
    app.config["DL_USERNAME"] = "admin"
    app.config["DL_PASSWORD"] = "admin"
    app.config["DL_CATEGORY"] = "audiobooks"
    yield app


@pytest.fixture
def setup_manager() -> Any:
    """Fixture that returns a setup_manager helper function."""

    def _setup(app: Flask, **kwargs: Any) -> TorrentManager:
        for k, v in kwargs.items():
            app.config[k] = v
        manager = TorrentManager()
        manager.init_app(app)
        return manager

    return _setup
