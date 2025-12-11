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

            scraper_core.fetch_and_parse_page(hostname, query, page, user_agent)

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
            scraper_core.fetch_and_parse_page(hostname, query, page, user_agent)


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
        results = scraper_core.fetch_and_parse_page(hostname, query, 1, "TestAgent/1.0")

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
        results = scraper_core.fetch_and_parse_page(hostname, query, 1, "TestAgent/1.0")

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
        results = scraper_core.fetch_and_parse_page(hostname, query, 1, "TestAgent/1.0")

    assert len(results) == 1
    r = results[0]
    assert r["language"] == "Unknown"
    assert r["category"] == "Unknown"
    assert r["post_date"] == "Unknown"
    assert r["format"] == "Unknown"
    assert r["bitrate"] == "Unknown"
    assert r["file_size"] == "Unknown"


# --- Get Book Details Tests ---


def test_get_book_details_sanitization(mock_sleep: Any) -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h1>Sanitized Book</h1></div>
        <div class="desc">
            <p style="color: red;">Allowed P tag.</p>
            <script>alert('XSS');</script>
            <b>Bold Text</b>
            <a href="http://bad.com">Malicious Link</a>
        </div>
    </div>
    """
    # FIX: Patch get_thread_session as that is what core.py imports/uses
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/book")

        description = str(details.get("description", ""))
        assert "<p>Allowed P tag.</p>" in description
        assert "style" not in description
        assert "<b>Bold Text</b>" in description
        assert "Malicious Link" in description
        assert "<a href" not in description
        assert "<script>" not in description


def test_get_book_details_caching(mock_sleep: Any) -> None:
    """Test that details are returned from cache."""
    url = "https://audiobookbay.lu/cached_details"
    # FIX: Explicit cast for mock cache entry
    expected = cast(BookDict, {"title": "Cached Details"})
    # FIX: Use the new details_cache instead of search_cache (which stores lists)
    # The cache is imported from scraper.core (which gets it from network)
    from audiobook_automated.scraper.network import details_cache

    details_cache[url] = expected

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session") as mock_session_getter:
        result = get_book_details(url)
        assert result == expected
        mock_session_getter.assert_not_called()


def test_get_book_details_success(details_html: str, mock_sleep: Any) -> None:
    # Cache cleared automatically by fixture
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = details_html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/valid-book")

        assert details["title"] == "A Game of Thrones"
        assert details["info_hash"] == "eb154ac7886539c4d01eae14908586e336cdb550"
        assert details["file_size"] == "1.37 GBs"


def test_get_book_details_default_cover_skip(mock_sleep: Any) -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h1>Book Default Cover</h1></div>
        <div class="postContent">
            <img itemprop="image" src="/images/default_cover.jpg">
        </div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/def-cover")
        assert details["cover"] is None


def test_get_book_details_failure(mock_sleep: Any) -> None:
    # FIX: Patch get_thread_session as that is what core.py imports/uses
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.RequestException("Net Down")

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        with pytest.raises(requests.exceptions.RequestException):
            get_book_details("https://audiobookbay.lu/fail-book")


def test_get_book_details_ssrf_protection() -> None:
    with pytest.raises(ValueError) as exc:
        get_book_details("https://google.com/admin")
    assert "Invalid domain" in str(exc.value)


def test_get_book_details_empty(mock_sleep: Any) -> None:
    with pytest.raises(ValueError) as exc:
        get_book_details("")
    assert "No URL provided" in str(exc.value)


def test_get_book_details_url_parse_error(mock_sleep: Any) -> None:
    with patch("audiobook_automated.scraper.core.urlparse", side_effect=Exception("Boom")):
        with pytest.raises(ValueError) as exc:
            get_book_details("http://anything")
    assert "Invalid URL format" in str(exc.value)


def test_get_book_details_missing_metadata(mock_sleep: Any) -> None:
    html = """<div class="post"><div class="postTitle"><h1>Empty Book</h1></div></div>"""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/empty")
        assert details["language"] == "Unknown"
        assert details["format"] == "Unknown"


def test_get_book_details_unknown_bitrate_normalization(mock_sleep: Any) -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h1>Unknown Bitrate</h1></div>
        <div class="postContent"><p>Bitrate: ?</p></div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/unknown")
        assert details["bitrate"] == "Unknown"


def test_get_book_details_partial_bitrate(mock_sleep: Any) -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h1>Partial Info</h1></div>
        <div class="postContent"><p>Bitrate: 128 Kbps</p></div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/partial_bitrate")
        assert details["format"] == "Unknown"
        assert details["bitrate"] == "128 Kbps"


def test_get_book_details_partial_format(mock_sleep: Any) -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h1>Partial Info</h1></div>
        <div class="postContent"><p>Format: MP3</p></div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/partial")
        assert details["format"] == "MP3"
        assert details["bitrate"] == "Unknown"


def test_get_book_details_content_without_metadata_labels(mock_sleep: Any) -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h1>No Metadata</h1></div>
        <div class="postContent"><p>Just text.</p></div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/no_meta")
        assert details["format"] == "Unknown"


def test_get_book_details_consistency_checks(mock_sleep: Any) -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h1>Mystery Details</h1></div>
        <div class="postInfo">Category: ? Language: ?</div>
        <div class="postContent">
            <p>Posted: ?</p>
            <p>Format: ?</p>
            <span class="author" itemprop="author">?</span>
            <span class="narrator" itemprop="author">?</span>
        </div>
        <table class="torrent_info">
            <tr><td>File Size:</td><td>?</td></tr>
        </table>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/mystery")
        assert details["language"] == "Unknown"
        assert details["category"] == "Unknown"
        assert details["post_date"] == "Unknown"
        assert details["format"] == "Unknown"
        assert details["author"] == "Unknown"
        assert details["narrator"] == "Unknown"
        assert details["file_size"] == "Unknown"


def test_get_book_details_info_hash_strategy_2(mock_sleep: Any) -> None:
    """Forces Strategy 2: Table structure is broken (no table.torrent_info)."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Strategy 2 Book</h1></div>
        <table>
            <tr>
                <td>Info Hash:</td>
                <td>1111111111222222222233333333334444444444</td>
            </tr>
        </table>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/strat2")
        assert details["info_hash"] == "1111111111222222222233333333334444444444"


def test_get_book_details_info_hash_strategy_3(mock_sleep: Any) -> None:
    """Forces Strategy 3: Regex fallback."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Strategy 3 Book</h1></div>
        <div class="desc">
            Some text containing the hash 5555555555666666666677777777778888888888 in the body.
        </div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/strat3")
        assert details["info_hash"] == "5555555555666666666677777777778888888888"


# --- Extract Magnet Link Tests ---


def test_extract_magnet_success(mock_sleep: Any) -> None:
    url = "https://audiobookbay.lu/book"
    # Mock return from get_book_details
    mock_details = cast(BookDict, {"info_hash": "abc123hash456", "trackers": ["http://tracker.com/announce"]})

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        # FIX: Patch the get_trackers function instead of the removed global
        with patch("audiobook_automated.scraper.core.get_trackers", return_value=[]):
            magnet, error = extract_magnet_link(url)
            assert error is None
            assert magnet is not None
            assert "magnet:?xt=urn:btih:abc123hash456" in magnet
            assert "tracker.com" in magnet


def test_extract_magnet_missing_info_hash(mock_sleep: Any) -> None:
    """Test behavior when get_book_details returns Unknown hash."""
    url = "https://audiobookbay.lu/book"
    mock_details = cast(BookDict, {"info_hash": "Unknown", "trackers": []})

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        magnet, error = extract_magnet_link(url)
        assert magnet is None
        assert error is not None
        assert "Info Hash could not be found" in error


def test_extract_magnet_ssrf_inherited(mock_sleep: Any) -> None:
    """Verifies that extract_magnet_link inherits the SSRF validation from get_book_details."""
    url = "https://google.com/evil"
    # Real logic: get_book_details raises ValueError for invalid domains
    with patch("audiobook_automated.scraper.core.get_book_details", side_effect=ValueError("Invalid domain")):
        magnet, error = extract_magnet_link(url)
        assert magnet is None
        assert error is not None
        assert "Invalid domain" in error


def test_extract_magnet_generic_exception(mock_sleep: Any) -> None:
    url = "https://audiobookbay.lu/book"
    with patch("audiobook_automated.scraper.core.get_book_details", side_effect=Exception("Database down")):
        with patch("audiobook_automated.scraper.core.logger") as mock_logger:
            magnet, error = extract_magnet_link(url)
            assert magnet is None
            assert error is not None
            assert "Database down" in error
            assert mock_logger.error.called


def test_extract_magnet_none_trackers(mock_sleep: Any) -> None:
    """Test extract_magnet_link handling when trackers is explicitly None."""
    url = "https://audiobookbay.lu/book"
    # Mock details where 'trackers' key exists but value is None
    # We cast to avoid MyPy errors, simulating runtime data that might violate TypedDict if not careful
    mock_details = cast(BookDict, {"info_hash": "abc123hash", "trackers": None})

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        # Patch get_trackers to return empty list
        with patch("audiobook_automated.scraper.core.get_trackers", return_value=[]):
            magnet, error = extract_magnet_link(url)

            assert error is None
            assert magnet is not None
            assert "magnet:?xt=urn:btih:abc123hash" in magnet
            # Should not contain any tr= parameters if configured trackers are also empty
            assert "&tr=" not in magnet
