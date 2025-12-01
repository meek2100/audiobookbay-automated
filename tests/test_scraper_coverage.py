import importlib
import logging
import os
from unittest.mock import MagicMock, mock_open, patch

import requests

from app import scraper


# --- Module-Level Logic Tests ---
def test_custom_mirrors_env(monkeypatch):
    monkeypatch.setenv("ABB_MIRRORS_LIST", "custom.mirror.com, another.mirror.net")
    importlib.reload(scraper)
    assert "custom.mirror.com" in scraper.ABB_FALLBACK_HOSTNAMES


def test_ua_init_exception():
    """
    Tests module-level initialization failure for UserAgent.
    CRITICAL: Must reload scraper in 'finally' to restore the real logger/module
    state, otherwise subsequent tests run with a Mock logger (breaking caplog)
    or an uninstrumented module (breaking coverage).
    """
    try:
        with patch("fake_useragent.UserAgent", side_effect=Exception("UA Init Failed")):
            with patch("logging.getLogger") as mock_get_logger:
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger

                # Reload triggers the exception during module init
                importlib.reload(scraper)

                assert scraper.ua_generator is None
                args, _ = mock_logger.warning.call_args
                assert "Failed to initialize fake_useragent" in args[0]
    finally:
        # Restore scraper to a clean, instrumented state with a REAL logger
        importlib.reload(scraper)


# --- Function Tests ---
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
        # Test Timeout specifically
        mock_session.head.side_effect = requests.Timeout("Timeout")
        result = scraper.check_mirror("timeout.mirror")
        assert result is None

        # Test RequestException specifically
        mock_session.head.side_effect = requests.RequestException("Error")
        result = scraper.check_mirror("error.mirror")
        assert result is None


def test_find_best_mirror_all_fail():
    scraper.mirror_cache.clear()
    with patch("app.scraper.check_mirror", return_value=None):
        result = scraper.find_best_mirror()
        assert result is None


def test_find_best_mirror_success():
    """Test the successful path where a mirror is found and returned."""
    scraper.mirror_cache.clear()
    # FIX: Patch the fallback list to a single item to prevent ThreadPool from
    # exhausting the side_effect with multiple parallel calls.
    with patch("app.scraper.ABB_FALLBACK_HOSTNAMES", ["mirror1.com"]):
        with patch("app.scraper.check_mirror", side_effect=["mirror1.com"]):
            result = scraper.find_best_mirror()
            assert result == "mirror1.com"


def test_get_random_user_agent_fallback():
    # Force ua_generator to None
    with patch("app.scraper.ua_generator", None):
        ua = scraper.get_random_user_agent()
        assert ua in scraper.FALLBACK_USER_AGENTS


def test_get_random_user_agent_exception():
    # Helper class to raise exception on property access
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
    # Force urlparse to raise exception (Mocking urlparse directly)
    with patch("app.scraper.urlparse", side_effect=Exception("Parse Error")):
        res, err = scraper.extract_magnet_link("http://some.url")
        assert res is None
        assert "Malformed URL" in err


def test_extract_magnet_http_error_code():
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 500  # Server error
        mock_session.get.return_value = mock_response

        magnet, error = scraper.extract_magnet_link("http://valid.url")
        assert magnet is None
        assert "Status Code: 500" in error


def test_extract_magnet_no_sibling_td():
    # Covers line where info_hash_row exists but no sibling
    html_content = """<html><body><table><tr><td>Info Hash</td></tr></table></body></html>"""
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_session.get.return_value = mock_response

        magnet, error = scraper.extract_magnet_link("http://valid.url")
        # Fallback regex fails too in this short HTML
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
        # Verify finally block executed via log message
        assert "Closing scraper session" in caplog.text
        mock_session.close.assert_called_once()


def test_extract_magnet_bs4_error():
    """Test when BeautifulSoup fails to parse (rare edge case)."""
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
    """Test where Regex.search returns None (no match found)."""
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">Title</a></h2></div>
        <div class="postInfo">Info</div>
        <div class="postContent">
            <p style="text-align:center;">Details</p>
        </div>
    </div>
    """
    session = MagicMock()
    session.get.return_value.text = html
    session.get.return_value.status_code = 200

    # Ensure none of the regexes find anything
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
    assert results[0]["format"] == "N/A"


def test_parsing_exceptions():
    """Test where Regex.search raises an Exception."""
    html = """<div class="post"><div class="postTitle"><h2><a href="/link">T</a></h2></div><div class="postInfo">I</div><div class="postContent"><p style="text-align:center">D</p></div></div>"""
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
    """
    Force an exception during post processing (the outer loop) to ensure 'continue' is hit.
    """
    session = MagicMock()
    session.get.return_value.text = "<html></html>"
    session.get.return_value.status_code = 200

    # Create a mock post that raises exception when .select_one is called
    mock_post = MagicMock()
    mock_post.select_one.side_effect = Exception("Post Error")

    with patch("app.scraper.BeautifulSoup") as mock_bs:
        mock_bs.return_value.select.return_value = [mock_post]

        with caplog.at_level(logging.ERROR):
            results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")

            assert results == []
            assert "Could not process a post" in caplog.text


def test_fetch_page_urljoin_exception():
    """Force an exception during URL joining to hit the outer except block."""
    html = """<div class="post"><div class="postTitle"><h2><a href="/link">T</a></h2></div></div>"""
    session = MagicMock()
    session.get.return_value.text = html
    session.get.return_value.status_code = 200

    with patch("app.scraper.urljoin", side_effect=Exception("Join Error")):
        results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")

    assert results == []
