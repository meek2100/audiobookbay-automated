import importlib
import os
from unittest.mock import MagicMock, mock_open, patch

from app import scraper

# --- Module-Level Logic Tests (Requires Reload) ---


def test_custom_mirrors_env(monkeypatch):
    """Test that ABB_MIRRORS_LIST env var extends the hostname list."""
    monkeypatch.setenv("ABB_MIRRORS_LIST", "custom.mirror.com, another.mirror.net")
    importlib.reload(scraper)
    assert "custom.mirror.com" in scraper.ABB_FALLBACK_HOSTNAMES
    assert "another.mirror.net" in scraper.ABB_FALLBACK_HOSTNAMES


def test_ua_init_exception():
    """Test fallback behavior when UserAgent fails to initialize."""
    with patch("app.scraper.UserAgent", side_effect=Exception("UA Init Failed")):
        with patch("app.scraper.logger") as mock_logger:
            importlib.reload(scraper)
            assert scraper.ua_generator is None
            # Verify the warning log
            args, _ = mock_logger.warning.call_args
            assert "Failed to initialize fake_useragent" in args[0]


# --- Existing & Extended Function Tests ---


def test_load_trackers_from_env(monkeypatch):
    monkeypatch.setenv("MAGNET_TRACKERS", "udp://env.tracker:1337,udp://env.tracker:6969")
    trackers = scraper.load_trackers()
    assert len(trackers) == 2
    assert "udp://env.tracker:1337" in trackers


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


def test_find_best_mirror_all_fail():
    scraper.mirror_cache.clear()
    with patch("app.scraper.check_mirror", return_value=None):
        result = scraper.find_best_mirror()
        assert result is None


def test_get_random_user_agent_fallback():
    # Force generator to None to test fallback list
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
        assert "aaaaaaaaaabbbbbbbbbbccccccccccdddddddddd" in magnet


def test_extract_magnet_bad_url():
    res, err = scraper.extract_magnet_link("")
    assert res is None
    assert "No URL" in err
    res, err = scraper.extract_magnet_link("not-a-url")
    assert res is None
    assert "Malformed URL" in err


def test_extract_magnet_network_error():
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_session.get.side_effect = Exception("Network Down")
        magnet, error = scraper.extract_magnet_link("http://valid.url")
        assert magnet is None
        assert "Network Down" in error


def test_search_audiobookbay_success():
    """Test full search flow with threading."""
    with patch("app.scraper.find_best_mirror", return_value="mirror.com"):
        # Mock get_session so we don't make real requests
        with patch("app.scraper.get_session"):
            # Mock the page parser directly to return a result
            with patch("app.scraper.fetch_and_parse_page", return_value=[{"title": "Test Book"}]):
                results = scraper.search_audiobookbay("query", max_pages=1)
                assert len(results) == 1
                assert results[0]["title"] == "Test Book"


def test_parse_post_exception_handling():
    html = """<div class="post"></div><div class="post"><div class="postTitle"><h2><a href="/link">Good</a></h2></div></div>"""
    session = MagicMock()
    session.get.return_value.text = html
    session.get.return_value.status_code = 200

    with patch("app.scraper.logger"):
        results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert len(results) == 1
    assert results[0]["title"] == "Good"
