# tests/scraper/test_network.py
import json
import os
from typing import Any, Generator
from unittest.mock import mock_open, patch

import pytest
import requests
from flask import Flask

from app.constants import DEFAULT_TRACKERS, USER_AGENTS
from app.scraper import network


@pytest.fixture
def mock_app_context(app: Flask) -> Generator[Flask, None, None]:
    """Fixture to provide app for network functions."""
    yield app


def test_get_trackers_from_env(mock_app_context: Any) -> None:
    # Clear cache before test
    network.get_trackers.cache_clear()

    mock_app_context.config["MAGNET_TRACKERS"] = ["udp://env.tracker:1337"]

    trackers = network.get_trackers()
    assert len(trackers) == 1
    assert trackers[0] == "udp://env.tracker:1337"


def test_get_trackers_from_json(mock_app_context: Any) -> None:
    network.get_trackers.cache_clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []  # Empty env

    with patch.dict(os.environ, {}, clear=True):
        mock_data = '["udp://json.tracker:80"]'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("os.path.exists", return_value=True):
                trackers = network.get_trackers()
                assert trackers == ["udp://json.tracker:80"]


def test_get_trackers_json_invalid_structure(mock_app_context: Any) -> None:
    """Test when trackers.json exists but contains a dict instead of a list."""
    network.get_trackers.cache_clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []

    with patch.dict(os.environ, {}, clear=True):
        # Mock data as a JSON object/dict, not a list
        mock_data = '{"key": "value"}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("os.path.exists", return_value=True):
                with patch("app.scraper.network.logger") as mock_logger:
                    trackers = network.get_trackers()
                    # Should fallback to defaults
                    assert trackers == DEFAULT_TRACKERS
                    # Verify the specific warning was logged
                    args, _ = mock_logger.warning.call_args
                    assert "trackers.json contains invalid data" in args[0]


def test_get_trackers_json_read_error(mock_app_context: Any) -> None:
    """Test when reading/parsing trackers.json raises an exception."""
    network.get_trackers.cache_clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []

    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", side_effect=json.JSONDecodeError("Expecting value", "doc", 0)):
            with patch("app.scraper.network.logger") as mock_logger:
                trackers = network.get_trackers()
                assert trackers == DEFAULT_TRACKERS
                # Verify exception logging
                args, _ = mock_logger.warning.call_args
                assert "Failed to load trackers.json" in args[0]


def test_get_trackers_defaults(mock_app_context: Any) -> None:
    network.get_trackers.cache_clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []

    with patch("os.path.exists", return_value=False):
        trackers = network.get_trackers()
        assert trackers == DEFAULT_TRACKERS


def test_get_mirrors_logic(mock_app_context: Any) -> None:
    """Test combining user config with defaults and deduplication."""
    mock_app_context.config["ABB_HOSTNAME"] = "primary.com"
    mock_app_context.config["ABB_MIRRORS"] = ["mirror1.com", "primary.com"]  # Duplicate primary

    mirrors = network.get_mirrors()

    # Order: Primary -> Extra -> Defaults
    assert mirrors[0] == "primary.com"
    assert mirrors[1] == "mirror1.com"
    assert "audiobookbay.lu" in mirrors
    # Ensure primary only appears once despite being in extra list
    assert mirrors.count("primary.com") == 1


def test_check_mirror_success_head() -> None:
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.return_value.status_code = 200
        result = network.check_mirror("good.mirror")
        assert result == "good.mirror"


def test_check_mirror_success_get_fallback() -> None:
    """Test fallback to GET if HEAD raises an exception."""
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.side_effect = requests.RequestException("Method Not Allowed")
        with patch("app.scraper.network.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            result = network.check_mirror("fallback.mirror")
            assert result == "fallback.mirror"


def test_check_mirror_head_500_fallback() -> None:
    """Test fallback to GET if HEAD returns a non-200 status."""
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.return_value.status_code = 500
        with patch("app.scraper.network.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            result = network.check_mirror("flaky.mirror")
            assert result == "flaky.mirror"


def test_check_mirror_get_exception() -> None:
    """Test check_mirror returns None if both HEAD and GET fail."""
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.side_effect = requests.RequestException("HEAD Failed")
        with patch("app.scraper.network.requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("GET Failed")
            result = network.check_mirror("bad.mirror")
            assert result is None


def test_find_best_mirror_all_fail(mock_app_context: Any) -> None:
    """Test that find_best_mirror returns None and caches failure if all mirrors fail."""
    network.mirror_cache.clear()
    network.failure_cache.clear()

    with patch("app.scraper.network.check_mirror", return_value=None):
        result = network.find_best_mirror()
        assert result is None
        # Verify negative cache was set
        assert "failure" in network.failure_cache


def test_find_best_mirror_success(mock_app_context: Any) -> None:
    """Test successful mirror finding updates the cache."""
    # Important: Clear caches to ensure we don't hit the negative cache from previous tests
    network.mirror_cache.clear()
    network.failure_cache.clear()

    # Mock get_mirrors to return a controlled list
    with patch("app.scraper.network.get_mirrors", return_value=["mirror1.com"]):
        with patch("app.scraper.network.check_mirror", side_effect=["mirror1.com"]):
            result = network.find_best_mirror()
            assert result == "mirror1.com"
            # Verify it was added to the positive cache
            assert network.mirror_cache["active_mirror"] == "mirror1.com"


def test_find_best_mirror_cached(mock_app_context: Any) -> None:
    """Test that find_best_mirror returns cached value directly."""
    # Clear caches to remove any negative cache
    network.mirror_cache.clear()
    network.failure_cache.clear()

    # Setup cache state manually
    network.mirror_cache["active_mirror"] = "cached-mirror.lu"

    # Execute - should return immediately without calling get_mirrors or checking them
    # We do NOT patch check_mirror here to prove it doesn't get called (would error if called)
    result = network.find_best_mirror()

    assert result == "cached-mirror.lu"
    # Clean up to avoid pollution
    network.mirror_cache.clear()


def test_find_best_mirror_negative_cache_hit(mock_app_context: Any) -> None:
    """Test that find_best_mirror returns None immediately if negative cache is set.

    Covers app/scraper/network.py lines 184-185 (Negative Cache hit).
    """
    # Clear caches
    network.mirror_cache.clear()
    network.failure_cache.clear()

    # Inject failure into negative cache
    network.failure_cache["failure"] = True

    with patch("app.scraper.network.logger") as mock_logger:
        # Patch check_mirror to verify it is NOT called
        with patch("app.scraper.network.check_mirror") as mock_check:
            result = network.find_best_mirror()

            assert result is None
            mock_check.assert_not_called()

            # Verify the debug log was triggered
            args, _ = mock_logger.debug.call_args
            assert "Negative Cache hit" in args[0]


def test_get_random_user_agent_returns_string() -> None:
    ua = network.get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 10
    assert ua in USER_AGENTS
