# File: tests/scraper/test_core.py
"""Unit tests for core scraping logic."""

import concurrent.futures
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from audiobook_automated.scraper.core import fetch_and_parse_page, search_audiobookbay


def test_fetch_page_missing_href() -> None:
    """Test fetch_and_parse_page handles post title missing href attribute gracefully."""
    # This covers lines 97-98 in scraper/core.py where we check if href exists

    # Mock HTML response: A post with a title link that has NO href
    html_content = """
    <html>
        <body>
            <div class="post">
                <div class="postTitle">
                    <h2><a>Title Without Href</a></h2>
                </div>
                <div class="postContent">
                    <img src="/cover.jpg" />
                    Some content
                </div>
                <div class="postInfo">Info</div>
            </div>
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.text = html_content
    mock_response.raise_for_status = MagicMock()

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.get_semaphore"):
            with patch("audiobook_automated.scraper.core.time.sleep"):  # Skip sleep
                with patch("audiobook_automated.scraper.core.logger") as mock_logger:
                    results = fetch_and_parse_page("audiobookbay.lu", "query", 1, "UserAgent", 30)

                    # Should return empty list because the only post was skipped
                    assert results == []

                    # Verify the warning was logged
                    mock_logger.warning.assert_called_with("Post title element missing href attribute. Skipping.")


def test_search_partial_failure() -> None:
    """Test that search continues and clears cache if one page fails but others succeed.

    This ensures line coverage for the exception handling block in the future loop.
    """
    # Mock data for a successful page
    success_result = [
        {
            "title": "Book 1",
            "link": "http://link1",
            "cover": None,
            "language": "En",
            "category": "Audio",
            "post_date": "2024",
            "format": "MP3",
            "bitrate": "128",
            "file_size": "100MB",
        }
    ]

    # Create futures: one succeeds, one raises an exception
    # FIX: Explicit type annotation required for strict mypy
    future_success: concurrent.futures.Future[list[dict[str, Any]]] = concurrent.futures.Future()
    future_success.set_result(success_result)

    future_failure: concurrent.futures.Future[list[dict[str, Any]]] = concurrent.futures.Future()
    # UPDATED: Raise ConnectionError to trigger the cache invalidation logic.
    # Generic errors (ValueError) are now swallowed without clearing cache to prevent thrashing.
    future_failure.set_exception(requests.ConnectionError("Network failed for page 2"))

    # We mock executor.submit to return our prepared futures
    # The order depends on the loop in search_audiobookbay (page 1, page 2...)
    with patch("audiobook_automated.scraper.core.executor") as mock_executor:
        mock_executor.submit.side_effect = [future_success, future_failure]

        # We also need to mock find_best_mirror so it doesn't try to ping real sites
        with patch("audiobook_automated.scraper.core.find_best_mirror", return_value="audiobookbay.lu"):
            # Mock the cache lock/clearing to verify it's called
            with patch("audiobook_automated.scraper.core.mirror_cache") as mock_mirror_cache:
                # Execute search for 2 pages
                results = search_audiobookbay("test_query", max_pages=2)

                # ASSERTIONS
                # 1. We should still get results from the successful page
                assert len(results) == 1
                assert results[0]["title"] == "Book 1"

                # 2. The cache should have been cleared due to the failure
                mock_mirror_cache.clear.assert_called_once()


def test_search_total_failure() -> None:
    """Test that search raises ConnectionError when all mirrors fail (return None)."""
    with patch("audiobook_automated.scraper.core.find_best_mirror", return_value=None):
        with pytest.raises(ConnectionError) as exc:
            search_audiobookbay("query")

        # Verify specific error message used in core.py
        assert "No reachable AudiobookBay mirrors" in str(exc.value)
