# File: tests/unit/clients/test_base.py
"""Unit tests for base client logic."""

from typing import Any

import pytest

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
    """Cover all branches of _format_size including recursion/loop and exceptions."""
    assert TorrentClientStrategy._format_size(input_bytes) == expected
