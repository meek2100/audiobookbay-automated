import importlib
import logging
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest
import requests
import requests_mock

from app import scraper
from app.scraper import (
    extract_magnet_link,
    fetch_and_parse_page,
    get_book_details,
    mirror_cache,
    search_audiobookbay,
)


# --- Patch time.sleep to avoid slow tests ---
@pytest.fixture(autouse=True)
def mock_sleep():
    """Globally mock time.sleep to speed up tests."""
    with patch("time.sleep") as mock_sleep:
        yield mock_sleep


# --- Standard Functional Tests ---

# Real HTML snippet from 'Regular Search - AudioBook Bay.html'
REAL_WORLD_HTML = """
<div class="post">
    <div class="postTitle">
        <h2><a href="/abss/a-game-of-thrones-chapterized/" rel="bookmark">A Game of Thrones (A Song of Ice and Fire, Book 1) (Chapterized) - George R. R. Martin</a></h2>
    </div>
    <div class="postInfo">
        Category: Adults&nbsp; Bestsellers&nbsp; Fantasy&nbsp; Literature&nbsp; <br>
        Language: English<span style="margin-left:100px;">Keywords: A Game of Thrones&nbsp; </span><br>
    </div>
    <div class="postContent">
        <div class="center">
            <p class="center">Shared by:<a href="#">jason444555</a></p>
            <p class="center">
                <a href="/abss/a-game-of-thrones-chapterized/">
                    <img src="/images/cover.jpg" alt="A Game of Thrones" width="250">
                </a>
            </p>
        </div>
        <p style="text-align:center;">
            Posted: 14 Sep 2021<br>
            Format: <span style="color:#a00;">M4B</span> / Bitrate: <span style="color:#a00;">96 Kbps</span><br>
            File Size: <span style="color:#00f;">1.37</span> GBs
        </p>
    </div>
</div>
"""

# FIX: Updated mock HTML to use <span> tags for Format and Bitrate.
# This matches the structure of the real website and allows the scraper's
# "Strategy 1" (find next sibling) to extract "M4B" cleanly.
DETAILS_HTML = """
<div class="post">
    <div class="postTitle"><h1>A Game of Thrones</h1></div>
    <div class="postInfo">
        Language: English
    </div>
    <div class="postContent">
        <img itemprop="image" src="/cover.jpg">
        <p>Format: <span>M4B</span> / Bitrate: <span>96 Kbps</span></p>
        <span class="author" itemprop="author">George R.R. Martin</span>
        <span class="narrator" itemprop="author">Roy Dotrice</span>
        <div class="desc">
            <p>This is a great book.</p>
            <a href="http://bad.com">Spam Link</a>
        </div>
    </div>
    <table class="torrent_info">
        <tr><td>Tracker:</td><td>udp://tracker.opentrackr.org:1337/announce</td></tr>
        <tr><td>File Size:</td><td>1.37 GBs</td></tr>
        <tr><td>Info Hash:</td><td>eb154ac7886539c4d01eae14908586e336cdb550</td></tr>
    </table>
</div>
"""


def test_fetch_and_parse_page_real_structure(mock_sleep):
    hostname = "audiobookbay.lu"
    query = "test"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=REAL_WORLD_HTML, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)

    # Verify sleep was called (Jitter test)
    assert mock_sleep.called

    # NEW: Verify the Referer header was actually sent (Anti-bot stealth check)
    last_request = adapter.last_request
    assert last_request is not None
    assert "Referer" in last_request.headers
    # Expecting homepage as referer for page 1
    assert last_request.headers["Referer"] == f"https://{hostname}"

    assert len(results) == 1
    book = results[0]
    assert "A Game of Thrones" in book["title"]
    assert book["language"] == "English"
    assert book["format"] == "M4B"
    assert book["bitrate"] == "96 Kbps"
    # Note: The scraper logic combines the number and the unit if they are adjacent nodes
    assert book["file_size"] == "1.37 GBs"
    assert book["post_date"] == "14 Sep 2021"
    assert book["link"] == "https://audiobookbay.lu/abss/a-game-of-thrones-chapterized/"


def test_fetch_and_parse_page_unknown_bitrate():
    """Test that a bitrate of '?' is normalized to 'Unknown'."""
    hostname = "audiobookbay.lu"
    query = "unknown_bit"
    page = 1
    user_agent = "TestAgent/1.0"

    # HTML snippet with a '?' bitrate
    html = """
    <div class="post">
        <div class="postTitle">
            <h2><a href="/abss/test/" rel="bookmark">Test Book</a></h2>
        </div>
        <div class="postInfo">Language: English</div>
        <div class="postContent">
            <p style="text-align:center;">
                Posted: 01 Jan 2024<br>
                Format: <span>MP3</span> / Bitrate: <span>?</span>
            </p>
        </div>
    </div>
    """

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=html, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)

    assert len(results) == 1
    assert results[0]["bitrate"] == "Unknown"


def test_fetch_and_parse_page_malformed():
    """Test resilience against empty/broken HTML"""
    hostname = "audiobookbay.lu"
    query = "bad"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri(
        "GET", f"https://{hostname}/page/{page}/?s={query}", text="<html><body></body></html>", status_code=200
    )

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)
    assert results == []


def test_fetch_and_parse_page_mixed_validity():
    """
    Test a page containing one valid post and one malformed post (missing title).
    This ensures the scraper continues to process valid items after encountering a bad one.
    """
    hostname = "audiobookbay.lu"
    query = "mixed"
    page = 1
    user_agent = "TestAgent/1.0"

    mixed_html = """
    <div class="post">
        <div class="postInfo">Broken Item Info</div>
    </div>
    <div class="post">
        <div class="postTitle">
            <h2><a href="/abss/valid-book/" rel="bookmark">Valid Book Title</a></h2>
        </div>
        <div class="postContent"></div>
    </div>
    """

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=mixed_html, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)

    assert len(results) == 1
    assert results[0]["title"] == "Valid Book Title"
    assert results[0]["link"] == "https://audiobookbay.lu/abss/valid-book/"


def test_parsing_structure_change():
    """
    Test that if the HTML structure changes (labels missing), the scraper defaults to 'N/A'
    instead of crashing.
    """
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postContent">
            <p style="text-align:center;">
                Just some random text here.
            </p>
        </div>
    </div>
    """
    session = MagicMock()
    session.get.return_value.text = html
    session.get.return_value.status_code = 200

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")

    assert len(results) == 1
    assert results[0]["format"] == "N/A"
    assert results[0]["bitrate"] == "N/A"


def test_fetch_and_parse_page_language_fallback():
    """
    Test that if the Language label is malformed or missing,
    it defaults to 'N/A' instead of crashing.
    """
    hostname = "audiobookbay.lu"
    query = "lang_test"
    page = 1
    user_agent = "TestAgent/1.0"

    # HTML with "Languages:" instead of "Language:" to break the regex
    html = """
    <div class="post">
        <div class="postTitle">
            <h2><a href="/abss/book/">Book Title</a></h2>
        </div>
        <div class="postInfo">
            Category: Fantasy <br>
            Languages: English <br>
        </div>
        <div class="postContent">
             <p>Posted: 01 Jan 2020</p>
        </div>
    </div>
    """

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=html, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)

    assert len(results) == 1
    assert results[0]["language"] == "N/A"


def test_get_text_after_label_exception():
    """
    Test that _get_text_after_label handles exceptions gracefully.
    This covers the `except Exception: return "N/A"` block.
    """
    mock_container = MagicMock()
    # Force an exception when .find() is called
    mock_container.find.side_effect = Exception("BS4 Internal Error")

    # Access the private function directly
    result = scraper._get_text_after_label(mock_container, "Label:")
    assert result == "N/A"


def test_get_text_after_label_fallback():
    """
    Test that _get_text_after_label returns 'N/A' if the label exists but no value follows.
    This covers the return 'N/A' at the end of the try block.
    """

    # Create a class that acts like a string AND has the BS4 method
    class FakeNavigableString(str):
        def find_next_sibling(self):
            return None

    mock_container = MagicMock()

    # We simulate finding "Format:"
    # This string has the label, but splitting by ":" gives ["Format", ""],
    # so the value part is empty, causing the function to fall through to "N/A".
    mock_label_node = FakeNavigableString("Format:")

    mock_container.find.return_value = mock_label_node

    result = scraper._get_text_after_label(mock_container, "Format:")
    assert result == "N/A"


def test_fetch_page_timeout():
    """Test that connection timeouts are raised (to allow cache invalidation)."""
    hostname = "audiobookbay.lu"
    query = "timeout"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", exc=requests.exceptions.Timeout)

    with pytest.raises(requests.exceptions.Timeout):
        fetch_and_parse_page(session, hostname, query, page, user_agent)


def test_extract_magnet_no_hash(mock_sleep):
    """Test handling of pages where info hash cannot be found."""
    details_url = "https://audiobookbay.lu/audiobook-details"
    broken_html = """<html><body><table><tr><td>Some other data</td></tr></table></body></html>"""

    with requests_mock.Mocker() as m:
        m.get(details_url, text=broken_html)
        magnet, error = extract_magnet_link(details_url)
        assert magnet is None
        assert "Info Hash could not be found" in error

    # Verify sleep was called (Jitter test)
    assert mock_sleep.called


def test_search_no_mirrors_raises_error():
    """Test that search raises ConnectionError when no mirrors are found."""
    mirror_cache.clear()
    with patch("app.scraper.find_best_mirror") as mock_find:
        mock_find.return_value = None
        with pytest.raises(ConnectionError) as exc:
            search_audiobookbay("test")
        assert "No reachable AudiobookBay mirrors" in str(exc.value)


def test_search_special_characters():
    """
    Test searching with special characters (e.g. spaces, ampersands).
    Ensures URL encoding is handled correctly.
    """
    hostname = "audiobookbay.lu"
    query = "Batman & Robin [Special Edition]"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/", text=REAL_WORLD_HTML, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)
    assert len(results) > 0


# --- Coverage & Edge Case Tests ---


def test_custom_mirrors_env(monkeypatch):
    monkeypatch.setenv("ABB_MIRRORS", "custom.mirror.com, another.mirror.net")
    importlib.reload(scraper)
    assert "custom.mirror.com" in scraper.ABB_FALLBACK_HOSTNAMES


def test_load_trackers_from_env(monkeypatch):
    monkeypatch.setenv("MAGNET_TRACKERS", "udp://env.tracker:1337")
    trackers = scraper.load_trackers()
    assert len(trackers) == 1


def test_load_trackers_from_json():
    with patch.dict(os.environ, {}, clear=True):
        mock_data = '["udp://json.tracker:80"]'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("os.path.exists", return_value=True):
                trackers = scraper.load_trackers()
                assert trackers == ["udp://json.tracker:80"]


def test_load_trackers_non_list_json():
    with patch.dict(os.environ, {}, clear=True):
        mock_data = '{"key": "value"}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("os.path.exists", return_value=True):
                trackers = scraper.load_trackers()
                assert len(trackers) > 0


def test_load_trackers_malformed_json():
    """Test that load_trackers gracefully handles malformed JSON files."""
    with patch.dict(os.environ, {}, clear=True):
        # Mocks a file open that works, but json.load triggers the exception
        with patch("builtins.open", mock_open(read_data="{invalid_json")):
            with patch("os.path.exists", return_value=True):
                with patch("app.scraper.logger") as mock_logger:
                    trackers = scraper.load_trackers()
                    # Ensure fallback trackers are returned
                    assert len(trackers) > 0
                    # Ensure the error was logged
                    args, _ = mock_logger.warning.call_args
                    assert "Failed to load trackers.json" in args[0]


def test_check_mirror_success_head():
    """Test that check_mirror returns hostname if HEAD succeeds."""
    with patch("app.scraper.requests.head") as mock_head:
        mock_head.return_value.status_code = 200
        result = scraper.check_mirror("good.mirror")
        assert result == "good.mirror"


def test_check_mirror_success_get_fallback():
    """Test that check_mirror falls back to GET if HEAD fails (timeout/error/405)."""
    with patch("app.scraper.requests.head") as mock_head:
        # Simulate HEAD failure
        mock_head.side_effect = requests.RequestException("Method Not Allowed")

        with patch("app.scraper.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            result = scraper.check_mirror("fallback.mirror")
            assert result == "fallback.mirror"


def test_check_mirror_fail_both():
    """Test that check_mirror returns None if both HEAD and GET fail."""
    with patch("app.scraper.requests.head") as mock_head:
        mock_head.side_effect = requests.RequestException("HEAD fail")
        with patch("app.scraper.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("GET fail")
            result = scraper.check_mirror("dead.mirror")
            assert result is None


def test_find_best_mirror_all_fail():
    scraper.mirror_cache.clear()
    with patch("app.scraper.check_mirror", return_value=None):
        result = scraper.find_best_mirror()
        assert result is None


def test_find_best_mirror_success():
    scraper.mirror_cache.clear()
    with patch("app.scraper.ABB_FALLBACK_HOSTNAMES", ["mirror1.com"]):
        with patch("app.scraper.check_mirror", side_effect=["mirror1.com"]):
            result = scraper.find_best_mirror()
            assert result == "mirror1.com"


def test_get_random_user_agent_returns_string():
    """Test that we always get a valid string UA from our hardcoded list."""
    ua = scraper.get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 10
    assert ua in scraper.USER_AGENTS


def test_extract_magnet_regex_fallback():
    url = "http://fake.url"
    html_content = """<html><body><p>Hash: aaaaaaaaaabbbbbbbbbbccccccccccdddddddddd</p></body></html>"""
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_session.get.return_value = mock_response

        magnet, error = scraper.extract_magnet_link(url)
        assert magnet is not None


def test_extract_magnet_missing_info_hash():
    url = "http://fake.url"
    html_content = """<html><body><p>No hash here</p></body></html>"""
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_session.get.return_value = mock_response

        magnet, error = scraper.extract_magnet_link(url)
        assert magnet is None
        assert "Info Hash could not be found" in error


def test_extract_magnet_bad_url():
    res, err = scraper.extract_magnet_link("")
    assert res is None
    assert "No URL" in err
    res, err = scraper.extract_magnet_link("not-a-url")
    assert res is None
    assert "Invalid URL" in err


def test_extract_magnet_malformed_url_exception():
    with patch("app.scraper.urlparse", side_effect=Exception("Parse Error")):
        res, err = scraper.extract_magnet_link("http://some.url")
        assert res is None
        assert "Malformed URL" in err


def test_extract_magnet_http_error_code():
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_session.get.return_value = mock_response

        magnet, error = scraper.extract_magnet_link("http://valid.url")
        assert magnet is None
        assert "Status Code: 500" in error


def test_extract_magnet_no_sibling_td():
    html_content = """<html><body><table><tr><td>Info Hash</td></tr></table></body></html>"""
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_session.get.return_value = mock_response

        magnet, error = scraper.extract_magnet_link("http://valid.url")
        assert magnet is None
        assert "Info Hash could not be found" in error


def test_extract_magnet_network_error(caplog):
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_session.get.side_effect = Exception("Network Down")

        with caplog.at_level(logging.DEBUG):
            magnet, error = scraper.extract_magnet_link("http://valid.url")

        assert magnet is None
        assert "Network Down" in error
        assert "Closing scraper session" in caplog.text
        mock_session.close.assert_called_once()


def test_extract_magnet_bs4_error():
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>"
        mock_session.get.return_value = mock_response

        with patch("app.scraper.BeautifulSoup", side_effect=Exception("Parse Fail")):
            magnet, error = scraper.extract_magnet_link("http://valid.url")
            assert magnet is None
            assert "Parse Fail" in error


def test_search_audiobookbay_success():
    with patch("app.scraper.find_best_mirror", return_value="mirror.com"):
        with patch("app.scraper.get_session"):
            with patch("app.scraper.fetch_and_parse_page", return_value=[{"title": "Test Book"}]):
                results = scraper.search_audiobookbay("query", max_pages=1)
                assert len(results) == 1


def test_search_thread_failure():
    scraper.search_cache.clear()
    scraper.mirror_cache.clear()
    with patch("app.scraper.find_best_mirror", return_value="mirror.com"):
        with patch("app.scraper.get_session"):
            with patch("app.scraper.fetch_and_parse_page", side_effect=Exception("Scrape Fail")):
                with patch("app.scraper.mirror_cache") as mock_cache:
                    results = scraper.search_audiobookbay("query", max_pages=1)
                    assert results == []
                    mock_cache.clear.assert_called()


def test_fetch_page_post_exception(caplog):
    session = MagicMock()
    session.get.return_value.text = "<html></html>"
    session.get.return_value.status_code = 200

    mock_post = MagicMock()
    # Simulate an error during element selection inside the loop
    mock_post.select_one.side_effect = Exception("Post Error")

    with patch("app.scraper.BeautifulSoup") as mock_bs:
        mock_bs.return_value.select.return_value = [mock_post]
        with caplog.at_level(logging.ERROR):
            results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")
            assert results == []
            assert "Could not process a post" in caplog.text


def test_fetch_page_urljoin_exception():
    # Use real HTML structure but mock urljoin to fail
    session = MagicMock()
    session.get.return_value.text = REAL_WORLD_HTML
    session.get.return_value.status_code = 200

    with patch("app.scraper.urljoin", side_effect=Exception("Join Error")):
        results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert results == []


def test_search_audiobookbay_generic_exception_in_thread():
    """
    Tests that the system robustly handles generic runtime errors (e.g. ArithmeticError)
    occurring within a scraper thread.
    """
    scraper.search_cache.clear()
    scraper.mirror_cache.clear()

    with patch("app.scraper.find_best_mirror", return_value="mirror.com"):
        with patch("app.scraper.get_session"):
            with patch("concurrent.futures.ThreadPoolExecutor") as MockExecutor:
                mock_future = MagicMock()
                mock_future.result.side_effect = ArithmeticError("Unexpected calculation error")
                mock_executor_instance = MockExecutor.return_value.__enter__.return_value
                mock_executor_instance.submit.return_value = mock_future

                with patch("concurrent.futures.as_completed", return_value=[mock_future]):
                    with patch.object(scraper.mirror_cache, "clear") as mock_mirror_clear:
                        with patch.object(scraper.search_cache, "clear") as mock_search_clear:
                            with patch("app.scraper.logger") as mock_logger:
                                results = scraper.search_audiobookbay("query", max_pages=1)
                                assert results == []
                                args, _ = mock_logger.error.call_args
                                assert "Page scrape failed" in args[0]
                                mock_mirror_clear.assert_called()
                                mock_search_clear.assert_called()


def test_extract_magnet_link_generic_exception():
    """Tests the generic catch-all block in extract_magnet_link."""
    url = "http://valid.url"
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_session.get.side_effect = ValueError("Generic parsing logic failure")

        with patch("app.scraper.logger") as mock_logger:
            magnet, error = scraper.extract_magnet_link(url)
            assert magnet is None
            assert "Generic parsing logic failure" in error
            assert mock_logger.error.called


def test_extract_magnet_success_table():
    """
    Tests successful magnet link extraction where the Info Hash is found
    in the HTML table (the primary method).
    """
    url = "http://valid.url/book"
    html_content = """
    <html><body><table>
        <tr><td>Info Hash:</td><td>  abc123hash456  </td></tr>
        <tr><td>Trackers:</td><td>http://tracker.com/announce</td></tr>
    </table></body></html>
    """

    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_session.get.return_value = mock_response

        with patch("app.scraper.DEFAULT_TRACKERS", []):
            magnet, error = scraper.extract_magnet_link(url)
            assert error is None
            assert "magnet:?xt=urn:btih:abc123hash456" in magnet
            assert "tracker.com" in magnet


def test_custom_mirrors_env_edge_cases(monkeypatch):
    """Test that an empty or comma-only env var doesn't break the mirror list."""
    monkeypatch.setenv("ABB_MIRRORS", ", ,  ,")
    importlib.reload(scraper)
    # It should not have added empty strings
    assert "" not in scraper.ABB_FALLBACK_HOSTNAMES
    assert " " not in scraper.ABB_FALLBACK_HOSTNAMES
    # Should still contain defaults
    assert "audiobookbay.lu" in scraper.ABB_FALLBACK_HOSTNAMES


def test_page_limit_invalid(monkeypatch, caplog):
    """
    Test that invalid PAGE_LIMIT triggers the ValueError catch block
    and logs a warning.
    """
    monkeypatch.setenv("PAGE_LIMIT", "invalid_int")

    with caplog.at_level(logging.WARNING):
        importlib.reload(scraper)

    assert scraper.PAGE_LIMIT == 3
    assert "Invalid PAGE_LIMIT in environment" in caplog.text


def test_fetch_and_parse_page_missing_cover_image():
    """Test when the cover image element is missing from the post."""
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

    results = scraper.fetch_and_parse_page(session, hostname, query, 1, "TestAgent/1.0")

    assert len(results) == 1
    # This assertion covers app/scraper.py:204
    assert results[0]["cover"] == "/static/images/default_cover.jpg"
    assert results[0]["language"] == "English"


def test_fetch_and_parse_page_missing_post_info():
    """Test when the postInfo element (containing language) is completely missing."""
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

    results = scraper.fetch_and_parse_page(session, hostname, query, 1, "TestAgent/1.0")

    assert len(results) == 1
    # This assertion covers app/scraper.py:219
    assert results[0]["language"] == "N/A"
    assert results[0]["post_date"] == "01 Jan 2025"


def test_get_book_details_success():
    """Test get_book_details parses content correctly based on real structure."""
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = DETAILS_HTML
        mock_session.return_value.get.return_value = mock_response

        # Use valid domain to pass SSRF check
        details = get_book_details("https://audiobookbay.lu/valid-book")

        assert details["title"] == "A Game of Thrones"
        assert details["info_hash"] == "eb154ac7886539c4d01eae14908586e336cdb550"
        assert details["file_size"] == "1.37 GBs"
        assert details["language"] == "English"
        assert details["format"] == "M4B"
        assert details["bitrate"] == "96 Kbps"
        assert details["author"] == "George R.R. Martin"
        assert details["narrator"] == "Roy Dotrice"
        assert "udp://tracker.opentrackr.org" in details["trackers"][0]
        assert "This is a great book" in details["description"]
        assert "Spam Link" in details["description"]  # Check text remains
        assert "href" not in details["description"]  # Check link removed


def test_get_book_details_failure():
    """Test get_book_details raises exception on network fail."""
    with patch("app.scraper.get_session") as mock_session:
        mock_session.return_value.get.side_effect = requests.exceptions.RequestException("Net Down")
        with pytest.raises(requests.exceptions.RequestException):
            # Use valid domain so it hits the network logic
            get_book_details("https://audiobookbay.lu/fail-book")


def test_get_book_details_ssrf_protection():
    """Test that get_book_details rejects non-ABB domains."""
    with pytest.raises(ValueError) as exc:
        # Attempt to scrape Google (or an internal IP)
        get_book_details("https://google.com/admin")

    assert "Invalid domain" in str(exc.value)


def test_get_book_details_empty():
    """Test that get_book_details raises ValueError when URL is empty."""
    with pytest.raises(ValueError) as exc:
        get_book_details("")
    assert "No URL provided" in str(exc.value)


def test_get_book_details_url_parse_error():
    """Test that get_book_details wraps urlparse exceptions."""
    # We mock urlparse to simulate a library-level failure
    with patch("app.scraper.urlparse", side_effect=Exception("Boom")):
        with pytest.raises(ValueError) as exc:
            # Input doesn't matter since we mocked the parser
            get_book_details("http://anything")
    assert "Invalid URL format" in str(exc.value)


def test_get_book_details_missing_metadata():
    """Test get_book_details when postInfo and metadata paragraph are missing."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Empty Book</h1></div>
        <div class="postContent">
            <div class="desc">Just description.</div>
        </div>
    </div>
    """
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/empty")

        assert details["language"] == "N/A"
        assert details["format"] == "N/A"
        assert details["bitrate"] == "N/A"


def test_get_book_details_unknown_bitrate_normalization():
    """Test get_book_details normalizes '?' bitrate."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Unknown Bitrate</h1></div>
        <div class="postContent">
            <p>Bitrate: ?</p>
        </div>
    </div>
    """
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/unknown")

        assert details["bitrate"] == "Unknown"


def test_get_book_details_partial_bitrate():
    """Test get_book_details with only Bitrate (no Format) to hit specific if branches."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Partial Info</h1></div>
        <div class="postContent">
            <p>Bitrate: 128 Kbps</p>
        </div>
    </div>
    """
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/partial_bitrate")

        assert details["format"] == "N/A"
        assert details["bitrate"] == "128 Kbps"


def test_get_book_details_partial_format():
    """Test get_book_details with only Format (no Bitrate) to hit specific if branches."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Partial Info</h1></div>
        <div class="postContent">
            <p>Format: MP3</p>
        </div>
    </div>
    """
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/partial")

        assert details["format"] == "MP3"
        assert details["bitrate"] == "N/A"


def test_get_book_details_content_without_metadata_labels():
    """
    Test get_book_details where content div exists and has paragraphs,
    but none contain 'Format:' or 'Bitrate:'.
    This forces the loop to complete naturally without hitting 'break'.
    """
    html = """
    <div class="post">
        <div class="postTitle"><h1>No Metadata</h1></div>
        <div class="postContent">
            <p>Just some text.</p>
            <p>Another paragraph without labels.</p>
        </div>
    </div>
    """
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/no_meta")

        # Assert defaults are returned
        assert details["format"] == "N/A"
        assert details["bitrate"] == "N/A"
