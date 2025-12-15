# tests/scraper/test_core.py
"""Unit tests for core scraping logic."""

import concurrent.futures
from typing import Any
from unittest.mock import patch

from audiobook_automated.scraper.core import search_audiobookbay


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
    future_failure.set_exception(ValueError("Parsing failed for page 2"))

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
