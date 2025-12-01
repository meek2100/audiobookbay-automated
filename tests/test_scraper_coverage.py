import importlib
import os
from unittest.mock import MagicMock, mock_open, patch

from app import scraper

# --- Module-Level Logic Tests ---


def test_custom_mirrors_env(monkeypatch):
    """Test that ABB_MIRRORS_LIST env var extends the hostname list."""
    monkeypatch.setenv("ABB_MIRRORS_LIST", "custom.mirror.com, another.mirror.net")
    importlib.reload(scraper)
    assert "custom.mirror.com" in scraper.ABB_FALLBACK_HOSTNAMES
    assert "another.mirror.net" in scraper.ABB_FALLBACK_HOSTNAMES


def test_ua_init_exception():
    """Test fallback behavior when UserAgent fails to initialize."""
    # Must patch the source library to affect the module reload
    with patch("fake_useragent.UserAgent", side_effect=Exception("UA Init Failed")):
        with patch("app.scraper.logger") as mock_logger:
            importlib.reload(scraper)
            assert scraper.ua_generator is None
            args, _ = mock_logger.warning.call_args
            assert "Failed to initialize fake_useragent" in args[0]


# --- Function Tests ---


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
    assert "Invalid URL" in err  # Fixed assertion


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
        with patch("app.scraper.get_session"):
            with patch("app.scraper.fetch_and_parse_page", return_value=[{"title": "Test Book"}]):
                results = scraper.search_audiobookbay("query", max_pages=1)
                assert len(results) == 1
                assert results[0]["title"] == "Test Book"


def test_parsing_exceptions():
    """
    Forces exceptions during the regex parsing blocks to ensure
    the 'except Exception: pass' lines are covered.
    """
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

    # Patch the regex SEARCH methods to raise exceptions
    with (
        patch("app.scraper.RE_LANGUAGE.search", side_effect=Exception("Lang Fail")),
        patch("app.scraper.RE_POSTED.search", side_effect=Exception("Posted Fail")),
        patch("app.scraper.RE_FORMAT.search", side_effect=Exception("Format Fail")),
        patch("app.scraper.RE_BITRATE.search", side_effect=Exception("Bitrate Fail")),
        patch("app.scraper.RE_FILESIZE.search", side_effect=Exception("Size Fail")),
    ):
        results = scraper.fetch_and_parse_page(session, "host", "q", 1, "ua")

    # Should still succeed, but fields will be "N/A"
    assert len(results) == 1
    assert results[0]["language"] == "N/A"
    assert results[0]["post_date"] == "N/A"
