# File: tests/scraper/test_network.py
# pyright: reportPrivateUsage=false
"""Tests for the network module."""

from typing import cast
from unittest.mock import MagicMock, mock_open, patch

import requests
from flask import Flask
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from audiobook_automated.constants import DEFAULT_TRACKERS, USER_AGENTS
from audiobook_automated.scraper import network
from audiobook_automated.scraper.network import (
    CACHE_LOCK,
    _local,
    find_best_mirror,
    get_ping_session,
    get_trackers,
    mirror_cache,
    shutdown_network,
    tracker_cache,
)


def test_find_best_mirror_failover(app: Flask) -> None:
    """Test that find_best_mirror fails over to the next mirror on error."""
    # Setup
    mirror_cache.clear()
    mirrors = ["mirror1.com", "mirror2.com"]

    # Mocking get_ping_session to control the behavior of head requests
    with patch("audiobook_automated.scraper.network.get_mirrors", return_value=mirrors):
        with patch("audiobook_automated.scraper.network.get_ping_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            # First mirror fails (Timeout), Second succeeds
            mock_response_ok = MagicMock()
            mock_response_ok.status_code = 200
            mock_response_ok.elapsed.total_seconds.return_value = 0.5

            # Configure side effects for the session.head call
            # First call raises Timeout, second returns OK response
            mock_session.head.side_effect = [requests.Timeout("Timeout"), mock_response_ok]

            # Execute
            best_mirror = find_best_mirror()

            # Assert
            assert best_mirror == "mirror2.com"
            assert mock_session.head.call_count == 2


# --- Merged Coverage Tests from test_network_coverage.py ---


def test_get_trackers_cache_hit(app: Flask) -> None:
    """Test that cached trackers are returned."""
    with CACHE_LOCK:
        tracker_cache.clear()
        tracker_cache["default"] = ["cached_tracker"]

    assert get_trackers() == ["cached_tracker"]

    with CACHE_LOCK:
        tracker_cache.clear()


def test_get_trackers_env_var(app: Flask) -> None:
    """Test loading trackers from environment variable."""
    with CACHE_LOCK:
        tracker_cache.clear()

    app.config["MAGNET_TRACKERS"] = ["env_tracker"]
    with app.app_context():
        assert get_trackers() == ["env_tracker"]


def test_get_trackers_file(app: Flask) -> None:
    """Test loading trackers from trackers.json."""
    with CACHE_LOCK:
        tracker_cache.clear()

    app.config["MAGNET_TRACKERS"] = []

    with patch("pathlib.Path.cwd") as mock_cwd:
        mock_file = MagicMock()
        mock_cwd.return_value = mock_file
        mock_file.__truediv__.return_value = mock_file
        mock_file.exists.return_value = True

        with patch("builtins.open", new_callable=MagicMock) as mock_open_file:
            mock_f = MagicMock()
            mock_open_file.return_value.__enter__.return_value = mock_f

            # Case 1: Valid List
            with patch("json.load", return_value=["file_tracker"]):
                with app.app_context():
                    assert get_trackers() == ["file_tracker"]
                    # Reset cache
                    with CACHE_LOCK:
                        tracker_cache.clear()

            # Case 2: Invalid Data (Dict)
            with patch("json.load", return_value={"key": "value"}):
                with app.app_context():
                    assert get_trackers() == DEFAULT_TRACKERS
                    with CACHE_LOCK:
                        tracker_cache.clear()

            # Case 3: Exception
            with patch("json.load", side_effect=Exception("Read Error")):
                with app.app_context():
                    assert get_trackers() == DEFAULT_TRACKERS


def test_get_ping_session_init(app: Flask) -> None:
    """Test initialization of ping session."""
    _local.ping_session = None
    session = get_ping_session()
    assert session is not None
    assert isinstance(session, requests.Session)
    assert _local.ping_session == session


def test_find_best_mirror_fallback_logic(app: Flask) -> None:
    """Test failover to GET when HEAD fails with 403/405 or exception."""
    network.mirror_cache.clear()
    network.failure_cache.clear()

    with patch("audiobook_automated.scraper.network.get_mirrors", return_value=["mirror1.com"]):
        with patch("audiobook_automated.scraper.network.get_ping_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            # Case 1: HEAD returns 403, GET succeeds
            mock_head_resp = MagicMock()
            mock_head_resp.status_code = 403
            mock_session.head.return_value = mock_head_resp

            mock_get_resp = MagicMock()
            mock_get_resp.status_code = 200
            # Ensure GET doesn't fail on close()
            mock_get_resp.close = MagicMock()
            mock_session.get.return_value = mock_get_resp

            assert find_best_mirror() == "mirror1.com"

            # Clear cache for next case
            network.mirror_cache.clear()

            # Case 2: HEAD raises RequestException, GET succeeds
            mock_session.head.side_effect = requests.RequestException("Error")
            assert find_best_mirror() == "mirror1.com"
            mock_session.head.side_effect = None  # Reset
            # Restore HEAD return value
            mock_session.head.return_value = mock_head_resp

            # Clear cache for next case
            network.mirror_cache.clear()

            # Case 3: Both Fail
            # HEAD fails (e.g. 500)
            mock_session.head.return_value.status_code = 500
            # GET raises Timeout
            mock_session.get.side_effect = requests.Timeout("Timeout")

            assert find_best_mirror() is None


def test_find_best_mirror_negative_cache(app: Flask) -> None:
    """Test negative caching (failure_cache)."""
    network.mirror_cache.clear()
    network.failure_cache.clear()

    # Force failure to set negative cache
    with patch("audiobook_automated.scraper.network.get_mirrors", return_value=[]):
        find_best_mirror()

    # Now valid mirrors exist but cache should block
    with patch("audiobook_automated.scraper.network.get_mirrors", return_value=["valid.com"]):
        # Negative cache logic uses time.time(), so we can't easily jump ahead without mocking time
        # But we can verify it returns None immediately
        assert find_best_mirror() is None


def test_shutdown_executors() -> None:
    """Test shutdown of executors."""
    # Use the public shutdown function directly
    # Mock the internal executor to ensure it gets called
    with patch("audiobook_automated.scraper.network._mirror_executor.shutdown") as mock_shutdown:
        shutdown_network()
        mock_shutdown.assert_called_with(wait=False, cancel_futures=True)


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
        # Ensure GET doesn't fail on close()
        mock_session.get.return_value.close = MagicMock()

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
        # Ensure GET doesn't fail on close()
        mock_session.get.return_value.close = MagicMock()

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


def test_check_mirror_timeout_fallback() -> None:
    """Test Fallback: check_mirror should try GET if HEAD times out."""
    with patch("audiobook_automated.scraper.network.get_ping_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        # HEAD times out
        mock_session.head.side_effect = requests.Timeout("Connection Timed Out")
        # GET succeeds
        mock_session.get.return_value.status_code = 200
        # Ensure GET doesn't fail on close()
        mock_session.get.return_value.close = MagicMock()

        result = network.check_mirror("timeout.mirror")

        assert result == "timeout.mirror"
        # CRITICAL ASSERTION: GET SHOULD BE CALLED
        mock_session.get.assert_called_once()


def test_find_best_mirror_cached(app: Flask) -> None:
    """Test that find_best_mirror returns cached value directly."""
    # Clear caches to remove any negative cache
    network.mirror_cache.clear()
    network.failure_cache.clear()

    # Setup cache state manually
    network.mirror_cache["active_mirror"] = "cached-mirror.lu"

    with app.app_context():
        # Execute - should return immediately without calling get_mirrors or checking them
        # We do NOT patch check_mirror here to prove it doesn't get called (would error if called)
        result = network.find_best_mirror()

        assert result == "cached-mirror.lu"
    # Clean up to avoid pollution
    network.mirror_cache.clear()


def test_find_best_mirror_negative_cache_hit(app: Flask) -> None:
    """Test that the function returns None immediately if negative cache is active."""
    # Inject failure into cache
    with network.CACHE_LOCK:
        network.failure_cache["failure"] = True

    with app.app_context():
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


def test_get_trackers_json_invalid_syntax(app: Flask) -> None:
    """Test when trackers.json exists but contains invalid JSON syntax."""
    network.tracker_cache.clear()
    app.config["MAGNET_TRACKERS"] = []

    with patch("pathlib.Path.exists", return_value=True):
        # Use mock_open but make the read return invalid JSON text
        with patch("builtins.open", mock_open(read_data="{invalid_json")):
            with patch("audiobook_automated.scraper.network.logger") as mock_logger:
                trackers = network.get_trackers()

                # Should fallback to defaults
                assert trackers == DEFAULT_TRACKERS

                # Verify warning was logged
                args, _ = mock_logger.warning.call_args
                # The actual message depends on the implementation, but it usually catches JSONDecodeError
                # checking for "Failed to load" or similar
                assert "Failed to load trackers.json" in args[0]
