"""Integration tests for security features (CSRF, Headers)."""

from typing import Generator

import pytest
from flask import Flask

from audiobook_automated import create_app


@pytest.fixture
def csrf_app() -> Generator[Flask, None, None]:
    """Fixture creating an app with CSRF protection explicitly ENABLED.

    Overrides the default test config which disables CSRF.
    """
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "SAVE_PATH_BASE": "/tmp/test_security",
            "SECRET_KEY": "test-security-secret",
            "WTF_CSRF_ENABLED": True,  # CRITICAL: Enable CSRF for this suite
        }
    )
    yield app


def test_search_page_renders_csrf_token(csrf_app: Flask) -> None:
    """Ensure the search page template actually includes the CSRF meta tag.

    This confirms that the frontend has the necessary token to perform actions.
    """
    client = csrf_app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    # Check for the meta tag that actions.js reads
    assert b'name="csrf-token"' in response.data


def test_send_endpoint_requires_csrf(csrf_app: Flask) -> None:
    """Ensure the API rejects POST requests that lack the CSRF token.

    Simulates a CSRF attack or a broken frontend client.
    """
    client = csrf_app.test_client()
    # Attempt a POST request without headers/token
    response = client.post("/send", json={"link": "http://example.com", "title": "Test"})

    # Should fail with 400 Bad Request (The CSRF token is missing)
    assert response.status_code == 400
    assert b"The CSRF token is missing" in response.data or b"CSRF token missing" in response.data


def test_delete_endpoint_requires_csrf(csrf_app: Flask) -> None:
    """Ensure the Delete endpoint is protected against CSRF."""
    client = csrf_app.test_client()
    response = client.post("/delete", json={"id": "123"})
    assert response.status_code == 400


def test_reload_library_endpoint_requires_csrf(csrf_app: Flask) -> None:
    """Ensure the Library Reload endpoint is protected."""
    client = csrf_app.test_client()
    response = client.post("/reload_library")
    assert response.status_code == 400
