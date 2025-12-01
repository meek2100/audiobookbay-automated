import importlib
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
    with patch("fake_useragent.UserAgent", side_effect=Exception("UA Init Failed")):
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            importlib.reload(scraper)
            assert scraper.ua_generator is None
            args, _ = mock_logger.warning.call_args
            assert "Failed to initialize fake_useragent" in args[0]


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


def test_get_random_user_agent_fallback():
    with patch("app.scraper.ua_generator", None):
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


def test_extract_magnet_network_error():
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_session.get.side_effect = Exception("Network Down")
        magnet, error = scraper.extract_magnet_link("http://valid.url")
        assert magnet is None
        assert "Network Down" in error


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

    mock_re = MagicMock()
    mock_re.search.return_value = None  # Force No Match

    with (
        patch("app.scraper.RE_LANGUAGE", mock_re),
        patch("app.scraper.RE_POSTED", mock_re),
        patch("app.scraper.RE_FORMAT", mock_re),
        patch("app.scraper.RE_BITRATE", mock_re),
        patch("app.scraper.RE_FILESIZE", mock_re),
    ):
        results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")

    assert len(results) == 1
    assert results[0]["language"] == "N/A"  # Should default to N/A


def test_parsing_exceptions():
    """Test where Regex.search raises an Exception."""
    html = """<div class="post"><div class="postTitle"><h2><a href="/link">T</a></h2></div><div class="postInfo">I</div><div class="postContent"><p>D</p></div></div>"""
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
