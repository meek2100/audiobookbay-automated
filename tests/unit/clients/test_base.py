# File: tests/unit/clients/test_base.py
"""Unit tests for base client logic."""

from typing import Any, override
from unittest.mock import MagicMock

import pytest

from audiobook_automated.clients.base import TorrentClientStrategy, TorrentStatus
from audiobook_automated.utils import format_size


class MockStrategy(TorrentClientStrategy):
    """Minimal implementation of abstract base class for testing."""

    @override
    def connect(self) -> None:
        pass

    @override
    def close(self) -> None:
        pass

    @override
    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        pass

    @override
    def remove_torrent(self, torrent_id: str) -> None:
        pass

    @override
    def get_status(self, category: str) -> list[TorrentStatus]:
        return []


def test_format_size_logic() -> None:
    """Verify that bytes are converted to human-readable strings correctly."""
    # Standard units
    assert format_size(500) == "500.00 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(1048576) == "1.00 MB"
    assert format_size(1073741824) == "1.00 GB"

    # Petabytes (Edge case)
    huge_number = 1024 * 1024 * 1024 * 1024 * 1024 * 5
    assert "5.00 PB" in format_size(huge_number)

    # Invalid inputs
    assert format_size(None) == "Unknown"
    assert format_size("not a number") == "Unknown"

    bad_input: Any = [1, 2]
    assert format_size(bad_input) == "Unknown"


@pytest.mark.parametrize(
    "input_bytes, expected",
    [
        (None, "Unknown"),
        ("invalid", "Unknown"),
        (500, "500.00 B"),
        (1024, "1.00 KB"),
        (1048576, "1.00 MB"),
        (1073741824, "1.00 GB"),
        (1099511627776, "1.00 TB"),
        (1125899906842624, "1.00 PB"),
        # Overflow case beyond typical parsing logic (handled by final return)
        (1152921504606846976, "1024.00 PB"),
    ],
)
def test_format_size_parameterized(input_bytes: Any, expected: str) -> None:
    """Cover all branches of format_size including recursion/loop and exceptions."""
    assert format_size(input_bytes) == expected


def test_strategy_cleanup() -> None:
    """Test that __del__ calls close()."""
    strategy = MockStrategy("host", 80, "u", "p")
    strategy.close = MagicMock()  # type: ignore

    # Simulate garbage collection
    strategy.__del__()
    strategy.close.assert_called_once()


def test_strategy_cleanup_error() -> None:
    """Test that errors in __del__ are suppressed."""
    strategy = MockStrategy("host", 80, "u", "p")
    strategy.close = MagicMock(side_effect=Exception("Close Error"))  # type: ignore

    # Should not raise
    strategy.__del__()
    strategy.close.assert_called_once()


def test_base_verify_credentials_failure() -> None:
    """Test verify_credentials returns False on exception."""
    strategy = MockStrategy("h", 1, "u", "p")
    strategy.connect = MagicMock(side_effect=Exception("Connection Failed"))  # type: ignore
    assert strategy.verify_credentials() is False


def test_base_verify_credentials_success() -> None:
    """Test verify_credentials returns True on success."""
    strategy = MockStrategy("h", 1, "u", "p")
    # connect is a pass in MockStrategy, so it succeeds
    assert strategy.verify_credentials() is True


def test_base_teardown() -> None:
    """Test teardown calls close."""
    strategy = MockStrategy("h", 1, "u", "p")
    strategy.close = MagicMock()  # type: ignore
    strategy.teardown()
    strategy.close.assert_called_once()


def test_torrent_status_state_normalization() -> None:
    """Test that TorrentStatus automatically normalizes raw state strings."""
    from audiobook_automated.clients.base import TorrentState, normalize_torrent_state

    # None and empty
    assert normalize_torrent_state(None) == TorrentState.UNKNOWN
    assert normalize_torrent_state("") == TorrentState.UNKNOWN

    # Exact and common prefixes
    assert normalize_torrent_state("downloading") == TorrentState.DOWNLOADING
    assert normalize_torrent_state("forcedDL") == TorrentState.DOWNLOADING
    assert normalize_torrent_state("stalledUP") == TorrentState.SEEDING
    assert normalize_torrent_state("uploading") == TorrentState.SEEDING
    assert normalize_torrent_state("pausedDL") == TorrentState.PAUSED
    assert normalize_torrent_state("stopped") == TorrentState.PAUSED
    assert normalize_torrent_state("stalledDL") == TorrentState.STALLED
    assert normalize_torrent_state("queuedUP") == TorrentState.QUEUED
    assert normalize_torrent_state("in_queue") == TorrentState.QUEUED
    assert normalize_torrent_state("checkingUP") == TorrentState.CHECKING
    assert normalize_torrent_state("verifying") == TorrentState.CHECKING
    assert normalize_torrent_state("finished") == TorrentState.COMPLETED
    assert normalize_torrent_state("done") == TorrentState.COMPLETED
    assert normalize_torrent_state("error") == TorrentState.ERROR
    assert normalize_torrent_state("failed") == TorrentState.ERROR

    # Heuristic substring matches
    assert normalize_torrent_state("custom_download_job") == TorrentState.DOWNLOADING
    assert normalize_torrent_state("active_seed_peer") == TorrentState.SEEDING
    assert normalize_torrent_state("user_pause_action") == TorrentState.PAUSED
    assert normalize_torrent_state("network_stalled_wait") == TorrentState.STALLED
    assert normalize_torrent_state("batch_queue_item") == TorrentState.QUEUED
    assert normalize_torrent_state("file_check_hash") == TorrentState.CHECKING
    assert normalize_torrent_state("fatal_fail_code") == TorrentState.ERROR
    assert normalize_torrent_state("completely_bizarre_xyz") == TorrentState.UNKNOWN

    # TorrentStatus post_init normalization
    status = TorrentStatus(id="1", name="Book", progress=50.0, state="stalledUP", size="1GB")
    assert status.state == "Seeding"

    status_enum = TorrentStatus(id="2", name="Book", progress=100.0, state=TorrentState.SEEDING, size="1GB")
    assert status_enum.state == "Seeding"
