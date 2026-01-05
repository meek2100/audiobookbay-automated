# File: tests/scraper/test_core_extra.py
"""Tests for extra core scraper functionality."""

from unittest.mock import MagicMock, patch

from flask import Flask

from audiobook_automated.scraper.core import search_audiobookbay


def test_search_pagination_cancellation(app: Flask) -> None:
    """Test that pagination stops and futures are cancelled when a page returns no results."""
    mock_future1 = MagicMock()
    mock_future1.result.return_value = [{"title": "Book 1"}]

    mock_future2 = MagicMock()
    mock_future2.result.return_value = []  # Empty results, triggers break

    mock_future3 = MagicMock()

    with (
        app.app_context(),
        patch("audiobook_automated.scraper.core.executor.submit") as mock_submit,
        patch("audiobook_automated.scraper.core.find_best_mirror", return_value="mirror.com"),
        patch("audiobook_automated.scraper.core.get_thread_session"),
    ):
        mock_submit.side_effect = [mock_future1, mock_future2, mock_future3]

        results = search_audiobookbay("test", max_pages=3)

        assert len(results) == 1
        assert results[0]["title"] == "Book 1"

        # Verify cancellation of the 3rd future
        mock_future3.cancel.assert_called_once()
