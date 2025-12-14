"""Unit tests for base client logic."""

from typing import Any

from audiobook_automated.clients.base import TorrentClientStrategy


def test_format_size_logic() -> None:
    """Verify that bytes are converted to human-readable strings correctly."""
    # Standard units
    assert TorrentClientStrategy._format_size(500) == "500.00 B"
    assert TorrentClientStrategy._format_size(1024) == "1.00 KB"
    assert TorrentClientStrategy._format_size(1048576) == "1.00 MB"
    assert TorrentClientStrategy._format_size(1073741824) == "1.00 GB"

    # Petabytes (Edge case)
    huge_number = 1024 * 1024 * 1024 * 1024 * 1024 * 5
    assert "5.00 PB" in TorrentClientStrategy._format_size(huge_number)

    # Invalid inputs
    assert TorrentClientStrategy._format_size(None) == "Unknown"
    assert TorrentClientStrategy._format_size("not a number") == "Unknown"

    bad_input: Any = [1, 2]
    assert TorrentClientStrategy._format_size(bad_input) == "Unknown"
