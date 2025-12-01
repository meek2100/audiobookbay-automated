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

    # Mock the magnet extraction/adding to avoid side effects
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
