# File: tests/functional/test_system.py
"""Functional tests for system-level behaviors (Splash Screen, Config Injection)."""

from collections.abc import Generator
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

from audiobook_automated import create_app


@pytest.fixture
def app() -> Generator[Flask]:
    """Create a configured Flask application for system tests."""
    # Patch the class method verify_credentials to return True.
    with patch("audiobook_automated.clients.manager.TorrentManager.verify_credentials", return_value=True):
        app = create_app()
        app.config.update(
            {
                "TESTING": True,
                "SAVE_PATH_BASE": "/tmp/test_downloads",
                "SPLASH_TITLE": "Test Title",
                "SPLASH_MESSAGE": "Test Message",
                "SPLASH_ENABLED": True,
            }
        )
        yield app


def test_splash_configuration_context(client: FlaskClient) -> None:
    """Verify splash configuration is correctly injected into templates."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode()

    # Check that the configured values are present in the HTML
    assert "Test Title" in html
    assert "Test Message" in html
    assert 'data-splash-enabled="True"' in html


def test_splash_disabled(client: FlaskClient) -> None:
    """Verify splash is hidden when disabled."""
    with patch("audiobook_automated.clients.manager.TorrentManager.verify_credentials", return_value=True):
        app = create_app()
        app.config.update(
            {
                "TESTING": True,
                "SAVE_PATH_BASE": "/tmp/test_downloads",
                "SPLASH_ENABLED": False,
            }
        )

        client = app.test_client()

        response = client.get("/")
        html = response.data.decode()
        assert 'id="splash-overlay"' not in html
