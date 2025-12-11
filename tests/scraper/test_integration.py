"""Integration tests for the scraper module."""

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from audiobook_automated.scraper import search_audiobookbay
from audiobook_automated.scraper.network import search_cache
from audiobook_automated.scraper.parser import BookDict

# --- Search & Flow Tests ---


def test_search_audiobookbay_success(mock_sleep: Any) -> None:
    """Standard success test."""
    with patch("audiobook_automated.scraper.core.find_best_mirror", return_value="mirror.com"):
        # FIX: Patch get_thread_session as that is what core.py imports/uses
        with patch("audiobook_automated.scraper.core.get_thread_session"):
            # FIX: Explicitly cast mock return value to list[BookDict]
            mock_results = cast(list[BookDict], [{"title": "Test Book"}])
            with patch("audiobook_automated.scraper.core.fetch_and_parse_page", return_value=mock_results):
                results = search_audiobookbay("query", max_pages=1)
                assert len(results) == 1
                assert results[0]["title"] == "Test Book"


def test_search_caching(mock_sleep: Any) -> None:
    """Test that search results are returned from cache if available."""
    query = "cached_query"
    # FIX: Explicitly typed list of BookDict
    expected_result = cast(list[BookDict], [{"title": "Cached Book"}])
    search_cache[query] = expected_result

    # Ensure no network calls are made
    with patch("audiobook_automated.scraper.core.find_best_mirror") as mock_mirror:
        results = search_audiobookbay(query)
        assert results == expected_result
        mock_mirror.assert_not_called()


def test_search_audiobookbay_sync_coverage(mock_sleep: Any) -> None:
    """Mock ThreadPoolExecutor to run synchronously for coverage."""
    mock_future = MagicMock()

    mock_future.result.return_value = cast(list[BookDict], [{"title": "Sync Book"}])

    with patch("audiobook_automated.scraper.core.executor") as mock_executor_instance:
        mock_executor_instance.submit.return_value = mock_future

        with patch("audiobook_automated.scraper.core.concurrent.futures.as_completed", return_value=[mock_future]):
            with patch("audiobook_automated.scraper.core.find_best_mirror", return_value="mirror.com"):
                # FIX: Patch get_thread_session as that is what core.py imports/uses
                with patch("audiobook_automated.scraper.core.get_thread_session"):
                    results = search_audiobookbay("query", max_pages=1)
                    assert len(results) == 1
                    assert results[0]["title"] == "Sync Book"


def test_search_no_mirrors_raises_error(mock_sleep: Any) -> None:
    with patch("audiobook_automated.scraper.core.find_best_mirror", return_value=None):
        with pytest.raises(ConnectionError) as exc:
            search_audiobookbay("test")
        assert "No reachable AudiobookBay mirrors" in str(exc.value)


def test_search_thread_failure(mock_sleep: Any) -> None:
    with patch("audiobook_automated.scraper.core.find_best_mirror", return_value="mirror.com"):
        # FIX: Patch get_thread_session as that is what core.py imports/uses
        with patch("audiobook_automated.scraper.core.get_thread_session"):
            with patch("audiobook_automated.scraper.core.fetch_and_parse_page", side_effect=Exception("Scrape Fail")):
                with patch("audiobook_automated.scraper.core.mirror_cache") as mock_cache:
                    results = search_audiobookbay("query", max_pages=1)
                    assert results == []
                    mock_cache.clear.assert_called()


def test_search_audiobookbay_generic_exception_in_thread(mock_sleep: Any) -> None:
    with patch("audiobook_automated.scraper.core.find_best_mirror", return_value="mirror.com"):
        # FIX: Patch get_thread_session as that is what core.py imports/uses
        with patch("audiobook_automated.scraper.core.get_thread_session"):
            with patch("audiobook_automated.scraper.core.executor") as mock_executor_instance:
                mock_future = MagicMock()
                mock_future.result.side_effect = ArithmeticError("Unexpected calculation error")
                mock_executor_instance.submit.return_value = mock_future

                with patch(
                    "audiobook_automated.scraper.core.concurrent.futures.as_completed", return_value=[mock_future]
                ):
                    with patch("audiobook_automated.scraper.core.mirror_cache") as mock_mirror_clear:
                        with patch("audiobook_automated.scraper.core.logger") as mock_logger:
                            results = search_audiobookbay("query", max_pages=1)
                            assert results == []
                            args, _ = mock_logger.error.call_args
                            assert "Page scrape failed" in args[0]
                            mock_mirror_clear.clear.assert_called()
