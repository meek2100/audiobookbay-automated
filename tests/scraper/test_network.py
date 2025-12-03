import importlib
import logging
import os
from unittest.mock import mock_open, patch

import requests

from app import scraper


def test_load_trackers_from_env(monkeypatch):
    monkeypatch.setenv("MAGNET_TRACKERS", "udp://env.tracker:1337")
    trackers = scraper.load_trackers()
    assert len(trackers) == 1
    assert trackers[0] == "udp://env.tracker:1337"


def test_load_trackers_from_json():
    with patch.dict(os.environ, {}, clear=True):
        mock_data = '["udp://json.tracker:80"]'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("os.path.exists", return_value=True):
                trackers = scraper.load_trackers()
                assert trackers == ["udp://json.tracker:80"]


def test_load_trackers_non_list_json():
    """Test that invalid JSON structure (dict instead of list) falls back to defaults."""
    with patch.dict(os.environ, {}, clear=True):
        mock_data = '{"key": "value"}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("os.path.exists", return_value=True):
                trackers = scraper.load_trackers()
                # Should return defaults (len > 0)
                assert len(trackers) > 0
                assert "udp://tracker.openbittorrent.com:80" in trackers


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


def test_custom_mirrors_env(monkeypatch):
    monkeypatch.setenv("ABB_MIRRORS", "custom.mirror.com, another.mirror.net")
    importlib.reload(scraper)
    assert "custom.mirror.com" in scraper.ABB_FALLBACK_HOSTNAMES


def test_custom_mirrors_env_edge_cases(monkeypatch):
    """Test that an empty or comma-only env var doesn't break the mirror list."""
    monkeypatch.setenv("ABB_MIRRORS", ", ,  ,")
    importlib.reload(scraper)
    # It should not have added empty strings
    assert "" not in scraper.ABB_FALLBACK_HOSTNAMES
    assert " " not in scraper.ABB_FALLBACK_HOSTNAMES
    # Should still contain defaults
    assert "audiobookbay.lu" in scraper.ABB_FALLBACK_HOSTNAMES


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
