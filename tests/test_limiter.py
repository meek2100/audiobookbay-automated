from unittest.mock import patch

import pytest

from app.app import limiter


@pytest.fixture(autouse=True)
def reset_limiter():
    """Automatically resets the rate limiter before each test in this module."""
    limiter.reset()
    yield


def test_rate_limit_enforced(client):
    """Test that the /send endpoint enforces the rate limit (60 per minute)."""
    # Force enable limiter for this test context
    client.application.config["RATELIMIT_ENABLED"] = True

    with patch("app.app.extract_magnet_link") as mock_extract, patch("app.app.torrent_manager") as mock_tm:
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
        mock_tm.add_magnet.return_value = None

        # Send 60 allowed requests (limit is 60/min)
        for _ in range(60):
            response = client.post("/send", json={"link": "http://example.com/book", "title": "Test Book"})
            assert response.status_code == 200

        # The 61st request should be blocked
        response = client.post("/send", json={"link": "http://example.com/book", "title": "Test Book"})
        assert response.status_code == 429  # Too Many Requests


def test_rate_limit_headers(client):
    """
    UNHAPPY PATH / INFRA: Test that rate limit headers are actually being returned.
    This ensures the Limiter is attached correctly to the app config.
    """
    # Flask-Limiter is disabled by default in testing; enable it to verify headers
    client.application.config["RATELIMIT_ENABLED"] = True

    with patch("app.app.extract_magnet_link") as mock_extract, patch("app.app.torrent_manager") as mock_tm:
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
        mock_tm.add_magnet.return_value = None

        response = client.post("/send", json={"link": "http://example.com/book", "title": "Header Test"})
        assert response.status_code == 200

        # Check for standard Flask-Limiter headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

        # Remaining should be less than Limit (60)
        remaining = int(response.headers["X-RateLimit-Remaining"])
        assert remaining < 60
