# File: tests/scraper/test_network.py
"""Tests for the network module, covering mirror management and tracker retrieval."""

import json
from collections.abc import Generator
from typing import Any, cast
from unittest.mock import mock_open, patch

import pytest
import requests
from flask import Flask
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from audiobook_automated.constants import DEFAULT_TRACKERS, USER_AGENTS
from audiobook_automated.scraper import network


@pytest.fixture
def mock_app_context(app: Flask) -> Generator[Flask]:
    """Fixture to provide app for network functions."""
    yield app


def test_get_trackers_cache_hit(mock_app_context: Any) -> None:
    """Test that get_trackers returns cached value if available."""
    # Pre-populate cache
    network.tracker_cache.clear()
    cached_data = ["udp://cached.tracker:1337"]
    network.tracker_cache["default"] = cached_data

    # Ensure config would otherwise return something else to prove cache was used
    mock_app_context.config["MAGNET_TRACKERS"] = ["udp://env.tracker:80"]

    trackers = network.get_trackers()
    assert trackers == cached_data


def test_get_trackers_from_env(mock_app_context: Any) -> None:
    """Test retrieving trackers solely from environment configuration."""
    # Clear cache before test
    network.tracker_cache.clear()

    mock_app_context.config["MAGNET_TRACKERS"] = ["udp://env.tracker:1337"]

    trackers = network.get_trackers()
    assert len(trackers) == 1
    assert trackers[0] == "udp://env.tracker:1337"


def test_get_trackers_from_json_file(mock_app_context: Any) -> None:
    """Test loading trackers from the optional JSON file."""
    network.tracker_cache.clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []  # Empty env

    # Mock pathlib.Path.exists to return True
    with patch("pathlib.Path.exists", return_value=True):
        mock_data = '["udp://json.tracker:80"]'
        # Mock open to return our JSON list
        with patch("builtins.open", mock_open(read_data=mock_data)):
            trackers = network.get_trackers()
            assert trackers == ["udp://json.tracker:80"]


def test_get_trackers_json_invalid_structure(mock_app_context: Any) -> None:
    """Test when trackers.json exists but contains a dict instead of a list."""
    network.tracker_cache.clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []

    with patch("pathlib.Path.exists", return_value=True):
        # Mock data as a JSON object/dict, not a list
        mock_data = '{"key": "value"}'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("audiobook_automated.scraper.network.logger") as mock_logger:
                trackers = network.get_trackers()
                # Should fallback to defaults
                assert trackers == DEFAULT_TRACKERS
                # Verify the specific warning was logged
                args, _ = mock_logger.warning.call_args
                assert "trackers.json contains invalid data" in args[0]


def test_get_trackers_json_read_error(mock_app_context: Any) -> None:
    """Test when reading/parsing trackers.json raises an exception."""
    network.tracker_cache.clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []

    with patch("pathlib.Path.exists", return_value=True):
        # Simulate invalid JSON syntax
        with patch("builtins.open", side_effect=json.JSONDecodeError("Expecting value", "doc", 0)):
            with patch("audiobook_automated.scraper.network.logger") as mock_logger:
                trackers = network.get_trackers()
                assert trackers == DEFAULT_TRACKERS
                # Verify exception logging
                args, _ = mock_logger.warning.call_args
                assert "Failed to load trackers.json" in args[0]


def test_get_trackers_defaults(mock_app_context: Any) -> None:
    """Test fallback to default trackers when config is empty and no JSON file exists."""
    network.tracker_cache.clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []

    with patch("pathlib.Path.exists", return_value=False):
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


def test_get_session_configuration() -> None:
    """Test that get_session configures retries and adapters correctly."""
    session = network.get_session()

    # Verify adapters are mounted
    assert "https://" in session.adapters
    assert "http://" in session.adapters

    adapter = cast(HTTPAdapter, session.adapters["https://"])
    retry = adapter.max_retries

    assert isinstance(retry, Retry)
    assert retry.total == 5
    assert retry.backoff_factor == 1
    assert 429 in retry.status_forcelist
    assert 503 in retry.status_forcelist


def test_get_ping_session_configuration() -> None:
    """Test that get_ping_session configures ZERO retries."""
    session = network.get_ping_session()
    adapter = cast(HTTPAdapter, session.adapters["https://"])
    retry = adapter.max_retries

    assert isinstance(retry, Retry)
    assert retry.total == 0
    assert retry.backoff_factor == 0


def test_get_ping_session_singleton() -> None:
    """Test that get_ping_session returns the same singleton instance."""
    # Reset thread-local singleton
    network._local.ping_session = None

    session1 = network.get_ping_session()
    session2 = network.get_ping_session()

    assert session1 is not None
    assert session1 is session2


def test_get_thread_session_initialization() -> None:
    """Test that get_thread_session creates a session and reuses it."""
    # Ensure we start with a clean state for this thread
    network._local.session = None

    # First call: Should create a new session
    session1 = network.get_thread_session()
    assert isinstance(session1, requests.Session)

    # Second call: Should return the EXACT SAME session object (reuse)
    session2 = network.get_thread_session()
    assert session1 is session2


def test_check_mirror_success_head() -> None:
    """Test verifying a mirror via a successful HEAD request."""
    with patch("audiobook_automated.scraper.network.get_ping_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        mock_session.head.return_value.status_code = 200
        result = network.check_mirror("good.mirror")
        assert result == "good.mirror"


def test_check_mirror_success_get_fallback() -> None:
    """Test fallback to GET if HEAD raises an exception."""
    with patch("audiobook_automated.scraper.network.get_ping_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        mock_session.head.side_effect = requests.RequestException("Method Not Allowed")
        mock_session.get.return_value.status_code = 200

        result = network.check_mirror("fallback.mirror")
        assert result == "fallback.mirror"


def test_check_mirror_head_500_fallback() -> None:
    """Test that HEAD 500 does NOT fallback to GET and returns None."""
    with patch("audiobook_automated.scraper.network.get_ping_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        mock_session.head.return_value.status_code = 500
        mock_session.get.return_value.status_code = 200

        result = network.check_mirror("flaky.mirror")
        assert result is None


def test_check_mirror_head_405_fallback() -> None:
    """Test fallback to GET if HEAD returns 405 Method Not Allowed."""
    with patch("audiobook_automated.scraper.network.get_ping_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        # HEAD returns 405
        mock_session.head.return_value.status_code = 405
        # GET returns 200
        mock_session.get.return_value.status_code = 200

        result = network.check_mirror("fallback.mirror")
        assert result == "fallback.mirror"
        # Verify both called
        mock_session.head.assert_called()
        mock_session.get.assert_called()


def test_check_mirror_get_exception() -> None:
    """Test check_mirror returns None if both HEAD and GET fail."""
    with patch("audiobook_automated.scraper.network.get_ping_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        mock_session.head.side_effect = requests.RequestException("HEAD Failed")
        mock_session.get.side_effect = requests.RequestException("GET Failed")

        result = network.check_mirror("bad.mirror")
        assert result is None


def test_check_mirror_timeout() -> None:
    """Test Fail-Fast: check_mirror should return None immediately on HEAD timeout."""
    with patch("audiobook_automated.scraper.network.get_ping_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        # HEAD times out
        mock_session.head.side_effect = requests.Timeout("Connection Timed Out")

        result = network.check_mirror("timeout.mirror")

        assert result is None
        # CRITICAL ASSERTION: GET should NOT be called if HEAD timed out
        mock_session.get.assert_not_called()


def test_find_best_mirror_all_fail(mock_app_context: Any) -> None:
    """Test that find_best_mirror returns None and caches failure if all mirrors fail."""
    network.mirror_cache.clear()
    network.failure_cache.clear()

    with patch("audiobook_automated.scraper.network.check_mirror", return_value=None):
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
    with patch("audiobook_automated.scraper.network.get_mirrors", return_value=["mirror1.com"]):
        with patch("audiobook_automated.scraper.network.check_mirror", side_effect=["mirror1.com"]):
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
    """Test that the function returns None immediately if negative cache is active."""
    # Inject failure into cache
    with network.CACHE_LOCK:
        network.failure_cache["failure"] = True

    # Attempt to find mirror (should skip all network calls)
    with patch("audiobook_automated.scraper.network.get_mirrors") as mock_get:
        result = network.find_best_mirror()
        assert result is None
        mock_get.assert_not_called()


def test_get_random_user_agent_returns_string() -> None:
    """Test that the user agent generator returns a string from the known list."""
    ua = network.get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 10
    assert ua in USER_AGENTS


def test_shutdown_network() -> None:
    """Test that the network shutdown handler correctly terminates executors."""
    # Patch the global executor in the network module
    with patch("audiobook_automated.scraper.network._mirror_executor") as mock_executor:
        # Call the private shutdown function explicitly
        network._shutdown_network()

        # Verify it called shutdown with correct params for Python 3.9+ behavior
        mock_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
