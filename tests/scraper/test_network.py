# tests/scraper/test_network.py
import importlib
import logging
import os
from unittest.mock import mock_open, patch

import requests

from app.scraper import network  # Import explicitly to reload the module itself


def test_load_trackers_from_env(monkeypatch):
    monkeypatch.setenv("MAGNET_TRACKERS", "udp://env.tracker:1337")
    trackers = network.load_trackers()
    assert len(trackers) == 1
    assert trackers[0] == "udp://env.tracker:1337"


def test_load_trackers_from_json():
    with patch.dict(os.environ, {}, clear=True):
        mock_data = '["udp://json.tracker:80"]'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("os.path.exists", return_value=True):
                trackers = network.load_trackers()
                assert trackers == ["udp://json.tracker:80"]


def test_load_trackers_non_list_json():
    with patch.dict(os.environ, {}, clear=True):
        mock_data = '{"key": "value"}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("os.path.exists", return_value=True):
                trackers = network.load_trackers()
                assert len(trackers) > 0
                assert "udp://tracker.openbittorrent.com:80" in trackers


def test_load_trackers_malformed_json():
    with patch.dict(os.environ, {}, clear=True):
        with patch("builtins.open", mock_open(read_data="{invalid_json")):
            with patch("os.path.exists", return_value=True):
                with patch("app.scraper.network.logger") as mock_logger:
                    trackers = network.load_trackers()
                    assert len(trackers) > 0
                    args, _ = mock_logger.warning.call_args
                    assert "Failed to load trackers.json" in args[0]


def test_custom_mirrors_env(monkeypatch):
    """
    Verifies that the environment shapes the application configuration.
    CRITICAL: Must reload the 'network' module specifically to update the global list.
    """
    monkeypatch.setenv("ABB_MIRRORS", "custom.mirror.com, another.mirror.net")
    importlib.reload(network)
    assert "custom.mirror.com" in network.ABB_FALLBACK_HOSTNAMES

    # CLOSING THE CIRCLE: Reset state for other tests
    monkeypatch.delenv("ABB_MIRRORS", raising=False)
    importlib.reload(network)


def test_custom_mirrors_env_edge_cases(monkeypatch):
    monkeypatch.setenv("ABB_MIRRORS", ", ,  ,")
    importlib.reload(network)
    assert "" not in network.ABB_FALLBACK_HOSTNAMES
    assert " " not in network.ABB_FALLBACK_HOSTNAMES
    assert "audiobookbay.lu" in network.ABB_FALLBACK_HOSTNAMES

    # Reset
    monkeypatch.delenv("ABB_MIRRORS", raising=False)
    importlib.reload(network)


def test_custom_mirrors_deduplication(monkeypatch):
    """
    Test that duplicate mirrors are removed while preserving order.
    This verifies the 'dict.fromkeys' optimization in network.py.
    """
    # audiobookbay.lu is default; adding it again should result in only one entry
    monkeypatch.setenv("ABB_MIRRORS", "audiobookbay.lu, unique.mirror.com, audiobookbay.lu")
    importlib.reload(network)

    # Should only appear once
    assert network.ABB_FALLBACK_HOSTNAMES.count("audiobookbay.lu") == 1
    # Verify unique mirror is present
    assert "unique.mirror.com" in network.ABB_FALLBACK_HOSTNAMES

    # Reset
    monkeypatch.delenv("ABB_MIRRORS", raising=False)
    importlib.reload(network)


def test_check_mirror_success_head():
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.return_value.status_code = 200
        result = network.check_mirror("good.mirror")
        assert result == "good.mirror"


def test_check_mirror_success_get_fallback():
    """Test fallback to GET if HEAD raises an exception."""
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.side_effect = requests.RequestException("Method Not Allowed")
        with patch("app.scraper.network.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            result = network.check_mirror("fallback.mirror")
            assert result == "fallback.mirror"


def test_check_mirror_head_500_fallback():
    """
    Test fallback to GET if HEAD returns a non-200 status (e.g. 500).
    This ensures the 'if response.status_code == 200' branch is fully covered (False case).
    """
    with patch("app.scraper.network.requests.head") as mock_head:
        # HEAD connects but returns Server Error
        mock_head.return_value.status_code = 500
        with patch("app.scraper.network.requests.get") as mock_get:
            # GET succeeds
            mock_get.return_value.status_code = 200
            result = network.check_mirror("flaky.mirror")
            assert result == "flaky.mirror"
            # Verify GET was actually called
            assert mock_get.called


def test_check_mirror_fail_both():
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.side_effect = requests.RequestException("HEAD fail")
        with patch("app.scraper.network.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("GET fail")
            result = network.check_mirror("dead.mirror")
            assert result is None


def test_find_best_mirror_all_fail():
    network.mirror_cache.clear()
    with patch("app.scraper.network.check_mirror", return_value=None):
        result = network.find_best_mirror()
        assert result is None


def test_find_best_mirror_success():
    network.mirror_cache.clear()
    with patch("app.scraper.network.ABB_FALLBACK_HOSTNAMES", ["mirror1.com"]):
        with patch("app.scraper.network.check_mirror", side_effect=["mirror1.com"]):
            result = network.find_best_mirror()
            assert result == "mirror1.com"


def test_get_random_user_agent_returns_string():
    ua = network.get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 10
    assert ua in network.USER_AGENTS


def test_get_headers_with_user_agent_and_referer():
    """Test that get_headers correctly uses provided user_agent and sets a referer."""
    test_ua = "Custom-Agent/1.0"
    test_ref = "https://example.com/previous"

    # Use the real function
    headers = network.get_headers(user_agent=test_ua, referer=test_ref)

    # Assert provided UA is used
    assert headers["User-Agent"] == test_ua
    # Assert Referer is set
    assert headers["Referer"] == test_ref
    # Assert other default headers are present
    assert "Accept" in headers


def test_page_limit_invalid(monkeypatch, caplog):
    monkeypatch.setenv("PAGE_LIMIT", "invalid_int")

    with caplog.at_level(logging.WARNING):
        importlib.reload(network)

    assert network.PAGE_LIMIT == 3
    assert "Invalid PAGE_LIMIT in environment" in caplog.text

    # Reset
    monkeypatch.delenv("PAGE_LIMIT", raising=False)
    importlib.reload(network)
