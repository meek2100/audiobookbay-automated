# File: tests/scraper/test_integration.py
"""Integration tests for the scraper module."""

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import requests
import requests_mock
from flask import Flask
from collections.abc import Generator

from audiobook_automated.scraper import search_audiobookbay
from audiobook_automated.scraper.network import search_cache
from audiobook_automated.scraper.parser import BookSummary

# --- Search & Flow Tests ---

@pytest.fixture(autouse=True)
def clear_search_cache_fixture() -> Generator[None, None, None]:
    """Clear the search cache before each test."""
    search_cache.clear()
    yield
    search_cache.clear()


def test_search_audiobookbay_success(mock_sleep: Any) -> None:
    """Standard success test."""
    with patch("audiobook_automated.scraper.core.find_best_mirror", return_value="mirror.com"):
        # FIX: Patch get_thread_session as that is what core.py imports/uses
        with patch("audiobook_automated.scraper.core.get_thread_session"):
            # FIX: Explicitly cast mock return value to list[BookSummary]
            mock_results = cast(list[BookSummary], [{"title": "Test Book"}])
            with patch("audiobook_automated.scraper.core.fetch_and_parse_page", return_value=mock_results):
                results = search_audiobookbay("query", max_pages=1)
                assert len(results) == 1
                assert results[0]["title"] == "Test Book"


def test_search_caching(mock_sleep: Any) -> None:
    """Test that search results are returned from cache if available."""
    query = "cached_query"
    max_pages = 1
    cache_key = f"{query}::{max_pages}"

    # FIX: Explicitly typed list of BookSummary
    expected_result = cast(list[BookSummary], [{"title": "Cached Book"}])
    search_cache[cache_key] = expected_result

    # Ensure no network calls are made
    with patch("audiobook_automated.scraper.core.find_best_mirror") as mock_mirror:
        # We must pass max_pages to match the cache key exactly
        results = search_audiobookbay(query, max_pages=max_pages)
        assert results == expected_result
        mock_mirror.assert_not_called()


def test_search_audiobookbay_sync_coverage(mock_sleep: Any) -> None:
    """Mock ThreadPoolExecutor to run synchronously for coverage."""
    mock_future = MagicMock()

    mock_future.result.return_value = cast(list[BookSummary], [{"title": "Sync Book"}])

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
    """Test that a ConnectionError is raised if no mirrors are reachable."""
    with patch("audiobook_automated.scraper.core.find_best_mirror", return_value=None):
        with pytest.raises(ConnectionError) as exc:
            search_audiobookbay("test")
        assert "No reachable AudiobookBay mirrors" in str(exc.value)


def test_search_thread_failure(mock_sleep: Any) -> None:
    """Test that exceptions within search threads result in empty results and cache clearing."""
    with patch("audiobook_automated.scraper.core.find_best_mirror", return_value="mirror.com"):
        # FIX: Patch get_thread_session as that is what core.py imports/uses
        with patch("audiobook_automated.scraper.core.get_thread_session"):
            # UPDATED: Use ConnectionError to ensure cache clearing is triggered
            with patch(
                "audiobook_automated.scraper.core.fetch_and_parse_page",
                side_effect=requests.ConnectionError("Scrape Fail"),
            ):
                with patch("audiobook_automated.scraper.core.mirror_cache") as mock_cache:
                    results = search_audiobookbay("query", max_pages=1)
                    assert results == []
                    mock_cache.clear.assert_called()


def test_search_audiobookbay_generic_exception_in_thread(mock_sleep: Any) -> None:
    """Test handling of unexpected exceptions (like ArithmeticError) inside threads."""
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
                            # UPDATED: Generic errors should NOT clear cache anymore
                            mock_mirror_clear.clear.assert_not_called()


# --- Pipeline Tests (using requests_mock) ---


def test_search_pipeline_success(app: Flask) -> None:
    """Test the full search pipeline from search to parsing results."""
    # Mock the search page HTML
    html_content = """
    <html>
        <body>
            <div class="post">
                <div class="postTitle">
                    <h2><a href="/audiobook-details">Test Audiobook</a></h2>
                </div>
                <div class="postContent">
                    <img src="/cover.jpg" />
                    <p>Posted: 01 Jan 2024</p>
                    <p>Format: MP3</p>
                    <p>Bitrate: 64 kbps</p>
                    <p>File Size: 100 MB</p>
                </div>
                <div class="postInfo">
                    Category: Sci-Fi Language: English
                </div>
            </div>
        </body>
    </html>
    """

    with requests_mock.Mocker() as m:
        # Mock the search request
        m.get("https://audiobookbay.lu/", text=html_content)

        # We need to mock the /page/1/ request as well because the scraper might use it
        # depending on implementation details of search_audiobookbay (it loops pages)
        m.get("https://audiobookbay.lu/page/1/?s=Test%20Query", text=html_content)
        m.get("https://audiobookbay.lu/?s=Test%20Query", text=html_content)

        # Run the search
        # Patch find_best_mirror to avoid network calls and randomness
        with (
            app.app_context(),
            patch("audiobook_automated.scraper.core.find_best_mirror", return_value="audiobookbay.lu"),
        ):
            results = search_audiobookbay("Test Query", max_pages=1)

        assert len(results) == 1
        book = results[0]
        assert book["title"] == "Test Audiobook"
        assert book["language"] == "English"
        assert "Sci-Fi" in book["category"]
        assert book["post_date"] == "01 Jan 2024"
        assert book["format"] == "MP3"
        assert book["bitrate"] == "64 kbps"
        assert book["file_size"] == "100 MB"


def test_search_pipeline_no_results(app: Flask) -> None:
    """Test search pipeline when no results are found."""
    html_content = "<html><body><div class='content'>No results found</div></body></html>"

    with requests_mock.Mocker() as m:
        m.get("https://audiobookbay.lu/?s=Nonexistent%20Book", text=html_content)
        m.get("https://audiobookbay.lu/page/1/?s=Nonexistent%20Book", text=html_content)

        with (
            app.app_context(),
            patch("audiobook_automated.scraper.core.find_best_mirror", return_value="audiobookbay.lu"),
        ):
            results = search_audiobookbay("Nonexistent Book", max_pages=1)

        assert len(results) == 0


def test_search_pipeline_network_error(app: Flask) -> None:
    """Test search pipeline handles network errors gracefully."""
    with requests_mock.Mocker() as m:
        # Simulate connection error
        m.get("https://audiobookbay.lu/?s=Test%20Query", exc=requests.exceptions.ConnectionError)
        m.get("https://audiobookbay.lu/page/1/?s=Test%20Query", exc=requests.exceptions.ConnectionError)

        with (
            app.app_context(),
            patch("audiobook_automated.scraper.core.find_best_mirror", return_value="audiobookbay.lu"),
        ):
            # Should return empty list or partial results (empty in this case)
            # The scraper catches the exception and logs it
            results = search_audiobookbay("Test Query", max_pages=1)

        assert len(results) == 0
