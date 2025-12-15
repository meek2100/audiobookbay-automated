# tests/security/test_core.py
"""Tests for core security features like CSRF, SSRF, and input sanitization."""

from typing import Any

import pytest

from audiobook_automated.constants import FALLBACK_TITLE
from audiobook_automated.scraper import get_book_details
from audiobook_automated.utils import sanitize_title


def test_csrf_protection_enabled(app: Any) -> None:
    """Verify that POST requests are rejected without a CSRF token.

    Checks when protection is actually enabled.
    """
    # Temporarily enable CSRF for this specific test
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()

    # Attempt a POST request without the token (simulating an attack)
    response = client.post("/send", json={"link": "http://test.com", "title": "Test Book"})

    # Should fail with 400 Bad Request (CSRF Error)
    assert response.status_code == 400
    assert b"The CSRF token is missing" in response.data or response.status_code == 400


def test_ssrf_protection_on_details_scrape() -> None:
    """Test that get_book_details rejects non-ABB domains.

    This prevents Server-Side Request Forgery (SSRF) attacks.
    """
    with pytest.raises(ValueError) as exc:
        get_book_details("https://google.com/admin")
    assert "Invalid domain" in str(exc.value)


def test_sanitize_simple_title() -> None:
    """Test basic title sanitization."""
    assert sanitize_title("Harry Potter") == "Harry Potter"


def test_sanitize_special_chars() -> None:
    """Test removal of filesystem-unsafe characters."""
    # Colons and slashes should be removed
    assert sanitize_title("Book: The Movie / Part 1") == "Book The Movie  Part 1"


def test_sanitize_windows_reserved() -> None:
    """Test handling of Windows reserved filenames."""
    assert sanitize_title("CON") == "CON_Safe"
    assert sanitize_title("nul") == "nul_Safe"
    assert sanitize_title("LPT1") == "LPT1_Safe"
    # Partial match should remain untouched
    assert sanitize_title("CONFERENCE") == "CONFERENCE"


def test_sanitize_strips_to_empty() -> None:
    """Test that a title composed only of illegal chars falls back safely."""
    # Ensure we test against the Single Source of Truth
    assert sanitize_title("...") == FALLBACK_TITLE
    assert sanitize_title("???") == FALLBACK_TITLE
