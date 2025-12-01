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
    mirror_cache,
    search_audiobookbay,
)

# --- Standard Functional Tests ---

REAL_WORLD_HTML = """
<div class="post">
    <div class="postTitle">
        <h2><a href="/abss/moster-walter-dean-myers/" rel="bookmark">Moster - Walter Dean Myers</a></h2>
    </div>
    <div class="postInfo">
        Category: Crime Full Cast General Fiction Teen & Young Adult <br>
        Language: English<span style="margin-left:100px;">Keywords: Black TRIAL </span><br>
    </div>
    <div class="postContent">
        <div class="center">
            <p class="center">Shared by:<a href="#">FissionMailed</a></p>
            <p class="center">
                <a href="/abss/moster-walter-dean-myers/">
                    <img src="/images/cover.jpg" alt="Walter Dean Myers Moster" width="250">
                </a>
            </p>
        </div>
        <p style="center;"></p>
        <p style="text-align:center;">
            Posted: 30 Nov 2025<br>
            Format: <span style="color:#a00;">MP3</span> / Bitrate: <span style="color:#a00;">96 Kbps</span><br>
            File Size: <span style="color:#00f;">106.91</span> MBs
        </p>
    </div>
</div>
"""


def test_fetch_and_parse_page_real_structure():
    hostname = "audiobookbay.lu"
    query = "test"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=REAL_WORLD_HTML, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)

    assert len(results) == 1
    book = results[0]
    assert book["title"] == "Moster - Walter Dean Myers"
    assert book["language"] == "English"
    assert book["format"] == "MP3"
    assert book["bitrate"] == "96 Kbps"
    assert book["file_size"] == "106.91 MBs"
    assert book["post_date"] == "30 Nov 2025"
    assert book["link"] == "https://audiobookbay.lu/abss/moster-walter-dean-myers/"
    assert book["cover"] == "https://audiobookbay.lu/images/cover.jpg"


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


def test_fetch_page_regex_miss():
    """
    Test a page where regex patterns for metadata fail to match (e.g. layout change).
    Ensures fields default to 'N/A' gracefully without crashing.
    """
    hostname = "audiobookbay.lu"
    query = "regex_miss"
    page = 1
    user_agent = "TestAgent/1.0"

    # HTML where labels exist but structure differs from regex expectations
    changed_html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/book">Book Title</a></h2></div>
        <div class="postInfo">Language-ISO: English</div>
        <div class="postContent">
            <p style="text-align:center;">
                Date: 2025 <br>
                Encoding: MP3 <br>
            </p>
        </div>
    </div>
    """

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=changed_html, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)

    assert len(results) == 1
    item = results[0]
    # Should be N/A because regexes for "Language:", "Posted:", etc. won't match "Language-ISO:", "Date:"
    assert item["language"] == "N/A"
    assert item["post_date"] == "N/A"
    assert item["format"] == "N/A"


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


def test_extract_magnet_no_hash():
    """Test handling of pages where info hash cannot be found."""
    details_url = "https://audiobookbay.lu/audiobook-details"
    broken_html = """<html><body><table><tr><td>Some other data</td></tr></table></body></html>"""

    with requests_mock.Mocker() as m:
        m.get(details_url, text=broken_html)
        magnet, error = extract_magnet_link(details_url)
        assert magnet is None
        assert "Info Hash could not be found" in error


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
    monkeypatch.setenv("ABB_MIRRORS_LIST", "custom.mirror.com, another.mirror.net")
    importlib.reload(scraper)
    assert "custom.mirror.com" in scraper.ABB_FALLBACK_HOSTNAMES


def test_ua_init_exception():
    """Tests module-level initialization failure for UserAgent."""
    try:
        with patch("fake_useragent.UserAgent", side_effect=Exception("UA Init Failed")):
            with patch("logging.getLogger") as mock_get_logger:
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger
                importlib.reload(scraper)
                assert scraper.ua_generator is None
                args, _ = mock_logger.warning.call_args
                assert "Failed to initialize fake_useragent" in args[0]
    finally:
        importlib.reload(scraper)


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


def test_load_trackers_json_fail():
    with patch.dict(os.environ, {}, clear=True):
        with patch("builtins.open", mock_open(read_data="invalid-json")):
            with patch("os.path.exists", return_value=True):
                trackers = scraper.load_trackers()
                assert len(trackers) > 0


def test_check_mirror_success():
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_session.head.return_value.status_code = 200
        result = scraper.check_mirror("good.mirror")
        assert result == "good.mirror"


def test_check_mirror_fail():
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_session.head.return_value.status_code = 404
        result = scraper.check_mirror("bad.mirror")
        assert result is None


def test_check_mirror_exception():
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_session.head.side_effect = requests.Timeout("Timeout")
        result = scraper.check_mirror("timeout.mirror")
        assert result is None

        mock_session.head.side_effect = requests.RequestException("Error")
        result = scraper.check_mirror("error.mirror")
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


def test_get_random_user_agent_fallback():
    with patch("app.scraper.ua_generator", None):
        ua = scraper.get_random_user_agent()
        assert ua in scraper.FALLBACK_USER_AGENTS


def test_get_random_user_agent_exception():
    class BrokenUA:
        @property
        def random(self):
            raise Exception("UA Error")

    with patch("app.scraper.ua_generator", BrokenUA()):
        ua = scraper.get_random_user_agent()
        assert ua in scraper.FALLBACK_USER_AGENTS


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


def test_parsing_no_matches():
    html = """<div class="post"><div class="postTitle"><h2><a href="/link">T</a></h2></div></div>"""
    session = MagicMock()
    session.get.return_value.text = html
    session.get.return_value.status_code = 200

    mock_re = MagicMock()
    mock_re.search.return_value = None

    with (
        patch("app.scraper.RE_LANGUAGE", mock_re),
        patch("app.scraper.RE_POSTED", mock_re),
        patch("app.scraper.RE_FORMAT", mock_re),
        patch("app.scraper.RE_BITRATE", mock_re),
        patch("app.scraper.RE_FILESIZE", mock_re),
    ):
        results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")

    assert len(results) == 1
    assert results[0]["language"] == "N/A"


def test_parsing_exceptions():
    html = """<div class="post"><div class="postTitle"><h2><a href="/link">T</a></h2></div></div>"""
    session = MagicMock()
    session.get.return_value.text = html
    session.get.return_value.status_code = 200

    mock_re = MagicMock()
    mock_re.search.side_effect = Exception("Regex Fail")

    with (
        patch("app.scraper.RE_LANGUAGE", mock_re),
        patch("app.scraper.RE_POSTED", mock_re),
        patch("app.scraper.RE_FORMAT", mock_re),
        patch("app.scraper.RE_BITRATE", mock_re),
        patch("app.scraper.RE_FILESIZE", mock_re),
    ):
        results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")

    assert len(results) == 1
    assert results[0]["language"] == "N/A"


def test_fetch_page_post_exception(caplog):
    session = MagicMock()
    session.get.return_value.text = "<html></html>"
    session.get.return_value.status_code = 200

    mock_post = MagicMock()
    mock_post.select_one.side_effect = Exception("Post Error")

    with patch("app.scraper.BeautifulSoup") as mock_bs:
        mock_bs.return_value.select.return_value = [mock_post]
        with caplog.at_level(logging.ERROR):
            results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")
            assert results == []
            assert "Could not process a post" in caplog.text


def test_fetch_page_urljoin_exception():
    html = """<div class="post"><div class="postTitle"><h2><a href="/link">T</a></h2></div></div>"""
    session = MagicMock()
    session.get.return_value.text = html
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


def test_fetch_page_regex_exceptions():
    """
    Tests that regex parsing exceptions (e.g., if re.search raises) are caught silently.
    This provides 100% coverage for the except blocks in fetch_and_parse_page.
    """
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">Title</a></h2></div>
        <div class="postInfo">Language: English</div>
        <div class="postContent">
            <p style="text-align:center;">
                Posted: 2023 <br>
                Format: MP3 <br>
                Bitrate: 128 <br>
                File Size: 100 MB
            </p>
        </div>
    </div>
    """
    session = MagicMock()
    session.get.return_value.text = html
    session.get.return_value.status_code = 200

    # Create a mock regex object that raises an exception when search() is called
    mock_re_fail = MagicMock()
    mock_re_fail.search.side_effect = Exception("Regex Fail")

    # Patch ALL regexes to fail. This ensures every try/except block is entered.
    with (
        patch("app.scraper.RE_LANGUAGE", mock_re_fail),
        patch("app.scraper.RE_POSTED", mock_re_fail),
        patch("app.scraper.RE_FORMAT", mock_re_fail),
        patch("app.scraper.RE_BITRATE", mock_re_fail),
        patch("app.scraper.RE_FILESIZE", mock_re_fail),
    ):
        results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")

    # We expect 1 result, but all fields should be "N/A" because regexes failed.
    assert len(results) == 1
    item = results[0]
    assert item["language"] == "N/A"
    assert item["post_date"] == "N/A"
    assert item["format"] == "N/A"
    assert item["bitrate"] == "N/A"
    assert item["file_size"] == "N/A"
