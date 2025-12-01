import unittest
from unittest.mock import patch

from app.app import app, limiter


class TestRateLimiter(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF for easier testing
        self.client = self.app.test_client()

        # Reset limiter storage
        limiter.reset()

    def test_rate_limit_enforced(self):
        """Test that the /send endpoint enforces the rate limit (10 per minute)."""

        # Mock the magnet extraction/adding to avoid side effects
        with patch("app.app.extract_magnet_link") as mock_extract, patch("app.app.torrent_manager") as mock_tm:
            mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
            mock_tm.add_magnet.return_value = None

            # Send 10 allowed requests
            for _ in range(10):
                response = self.client.post("/send", json={"link": "http://example.com/book", "title": "Test Book"})
                self.assertEqual(response.status_code, 200)

            # The 11th request should be blocked
            response = self.client.post("/send", json={"link": "http://example.com/book", "title": "Test Book"})
            self.assertEqual(response.status_code, 429)  # Too Many Requests
