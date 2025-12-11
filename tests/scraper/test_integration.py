"""Integration tests for the scraper module."""

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import requests
import requests_mock

from audiobook_automated.scraper import core as scraper_core
from audiobook_automated.scraper import extract_magnet_link, get_book_details, search_audiobookbay
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


def test_search_special_characters(real_world_html: str, mock_sleep: Any) -> None:
    """Test that special characters in queries are passed correctly to the session."""
    hostname = "audiobookbay.lu"
    query = "Batman & Robin [Special Edition]"
    page = 1
    user_agent = "TestAgent/1.0"

    mock_session = requests.Session()
    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        with patch.object(mock_session, "get") as mock_get:
            mock_get.return_value.text = real_world_html
            mock_get.return_value.status_code = 200

            scraper_core.fetch_and_parse_page(hostname, query, page, user_agent, 30)

            # Verify the query was passed in the params dict
            mock_get.assert_called()
            call_args = mock_get.call_args
            assert call_args[1]["params"]["s"] == query


def test_fetch_page_timeout(mock_sleep: Any) -> None:
    hostname = "audiobookbay.lu"
    query = "timeout"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", exc=requests.exceptions.Timeout)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=session):
        with pytest.raises(requests.exceptions.Timeout):
            scraper_core.fetch_and_parse_page(hostname, query, page, user_agent, 30)


def test_fetch_and_parse_page_missing_cover_image(mock_sleep: Any) -> None:
    hostname = "audiobookbay.lu"
    query = "no_cover"
    html = """
    <div class="post">
        <div class="postTitle">
            <h2><a href="/abss/test-book/" rel="bookmark">Missing Cover Test</a></h2>
        </div>
        <div class="postInfo">Language: English</div>
        <div class="postContent">
            <p style="text-align:center;">Posted: 01 Jan 2025</p>
        </div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/1/?s={query}", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=session):
        results = scraper_core.fetch_and_parse_page(hostname, query, 1, "TestAgent/1.0", 30)

    assert len(results) == 1
    assert results[0]["cover"] is None
    assert results[0]["language"] == "English"


def test_fetch_and_parse_page_missing_post_info(mock_sleep: Any) -> None:
    hostname = "audiobookbay.lu"
    query = "no_info"
    html = """
    <div class="post">
        <div class="postTitle">
            <h2><a href="/abss/test-book/" rel="bookmark">Missing Info Test</a></h2>
        </div>
        <div class="postContent">
            <p style="text-align:center;">
                <a href="/abss/test-book/">
                    <img src="/images/cover.jpg" alt="Test" width="250">
                </a>
            </p>
            <p style="text-align:center;">Posted: 01 Jan 2025</p>
        </div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/1/?s={query}", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=session):
        results = scraper_core.fetch_and_parse_page(hostname, query, 1, "TestAgent/1.0", 30)

    assert len(results) == 1
    assert results[0]["language"] == "Unknown"
    assert results[0]["post_date"] == "01 Jan 2025"


def test_fetch_and_parse_page_consistency_checks(mock_sleep: Any) -> None:
    """Test that '?' values in metadata are converted to 'Unknown'.

    FIX: HTML structure updated to place all metadata in the same paragraph as 'Posted:',
    ensuring 'details_paragraph' logic finds them and triggers the '?' conversion logic.
    """
    hostname = "audiobookbay.lu"
    query = "question_marks"
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/book">Mystery Book</a></h2></div>
        <div class="postInfo">Category: ? Language: ?</div>
        <div class="postContent">
            <p>Posted: ?<br>Format: ?<br>Bitrate: ?<br>File Size: ?</p>
        </div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/1/?s={query}", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=session):
        results = scraper_core.fetch_and_parse_page(hostname, query, 1, "TestAgent/1.0", 30)

    assert len(results) == 1
    r = results[0]
    assert r["language"] == "Unknown"
    assert r["category"] == "Unknown"
    assert r["post_date"] == "Unknown"
    assert r["format"] == "Unknown"
    assert r["bitrate"] == "Unknown"
    assert r["file_size"] == "Unknown"


# --- Get Book Details Tests ---
# ... (rest of file is details tests, unchanged) ...
