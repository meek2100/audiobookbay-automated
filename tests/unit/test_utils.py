# File: tests/unit/test_utils.py
"""Unit tests for utility functions."""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pytest import LogCaptureFixture

from audiobook_automated.constants import FALLBACK_TITLE, SAFE_SUFFIX
from audiobook_automated.utils import (
    calculate_static_hash,
    construct_safe_save_path,
    ensure_collision_safety,
    format_size,
    get_application_version,
    sanitize_title,
)


def test_sanitize_title_basic() -> None:
    """Test basic title sanitization."""
    assert sanitize_title("Valid Title") == "Valid Title"
    assert sanitize_title("Title: Subtitle") == "Title Subtitle"
    assert sanitize_title("Title/With/Slashes") == "TitleWithSlashes"


def test_sanitize_title_empty() -> None:
    """Test sanitization of empty or invalid titles."""
    assert sanitize_title(None) == FALLBACK_TITLE
    assert sanitize_title("") == FALLBACK_TITLE
    assert sanitize_title("   ") == FALLBACK_TITLE
    # "..." strips to empty string
    assert sanitize_title("...") == FALLBACK_TITLE


def test_sanitize_title_windows_reserved() -> None:
    """Test sanitization of Windows reserved names."""
    assert sanitize_title("CON") == f"CON{SAFE_SUFFIX}"
    assert sanitize_title("con.txt") == f"con.txt{SAFE_SUFFIX}"
    assert sanitize_title("LPT1") == f"LPT1{SAFE_SUFFIX}"


def test_ensure_collision_safety_clean() -> None:
    """Test that safe titles are returned unchanged."""
    title = "My Safe Book"
    assert ensure_collision_safety(title) == title


def test_ensure_collision_safety_collision() -> None:
    """Test that collision-prone titles get a UUID appended."""
    # Mock uuid to get a predictable value
    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "12345678" * 4  # 32 chars

        # Test 1: Fallback Title
        result = ensure_collision_safety(FALLBACK_TITLE)
        expected = f"{FALLBACK_TITLE}_12345678"
        assert result == expected

        # Test 2: Safe Suffix (Reserved Name)
        unsafe = f"CON{SAFE_SUFFIX}"
        result = ensure_collision_safety(unsafe)
        expected = f"{unsafe}_12345678"
        assert result == expected


def test_ensure_collision_safety_max_length() -> None:
    """Test that titles exceeding max_length are truncated and get a UUID."""
    # Mock uuid
    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "12345678" * 4
        # UUID suffix is _12345678 (9 chars)

        # Title: "123456789012345" (15 chars)
        # Max: 10
        # Expected Logic:
        # trunc_len = max_length(10) - 9 = 1
        # Prefix = title[:1] = "1"
        # Suffix = "_12345678"
        # Result = "1_12345678" (Total 10 chars)

        title = "123456789012345"
        result = ensure_collision_safety(title, max_length=10)
        assert len(result) == 10
        assert result == "1_12345678"


def test_ensure_collision_safety_short_max_length() -> None:
    """Test max_length logic when the allowed length is extremely short (< 9).

    This forces trunc_len to be < 1, triggering the safety floor of 1.
    """
    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "12345678" * 4

        title = "ShortTitle"
        # If max_length is 5, reserved is 9.
        # trunc_len = 5 - 9 = -4.
        # Logic should force trunc_len = 1.
        # Result = "S" (1 char) + "_12345678" (9 chars) = "S_12345678" (10 chars total)
        # Note: The function returns a string LONGER than max_length in this extreme edge case
        # to ensure uniqueness/validity over strict length adherence (safety > strictness).
        result = ensure_collision_safety(title, max_length=5)
        assert result == "S_12345678"


def test_construct_safe_save_path_windows_path() -> None:
    """Test that construct_safe_save_path handles Windows paths correctly."""
    base_path = "C:\\Downloads"
    title = "My Book"
    # Should use PureWindowsPath
    expected = "C:\\Downloads\\My Book"
    assert construct_safe_save_path(base_path, title) == expected


def test_construct_safe_save_path_windows_reserved_collision_logic() -> None:
    """Test that Windows reserved names trigger UUID collision safety even on Linux paths.

    This simulates the app running on Linux (Docker) but saving to a Windows SMB share/path structure.
    """
    # Simulate a path structure that implies Windows (backslashes)
    base_path = r"\\Server\Share\Books"
    # Reserved name
    unsafe_title = "CON"

    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "12345678" * 4

        # Expected flow:
        # 1. sanitize_title("CON") -> "CON_Safe"
        # 2. ensure_collision_safety("CON_Safe") -> "CON_Safe_12345678" (due to _Safe suffix trigger)
        # 3. PureWindowsPath join
        result = construct_safe_save_path(base_path, unsafe_title)

        expected_suffix = "12345678"
        # We check that the result contains the safe suffix AND the uuid
        assert "CON_Safe" in result
        assert expected_suffix in result
        # Check path separators
        assert "\\" in result


def test_get_application_version_os_error(tmp_path: Path) -> None:
    """Test get_application_version handles OSError when reading version.txt."""
    version_file = tmp_path / "version.txt"
    version_file.write_text("hash")

    # Use a subdir so parent is tmp_path
    static_folder = tmp_path / "static"
    static_folder.mkdir()

    with patch("pathlib.Path.read_text", side_effect=OSError("Read error")):
        with patch(
            "audiobook_automated.utils.calculate_static_hash",
            return_value="calculated_v1",
        ) as mock_calc:
            version = get_application_version(static_folder)
            assert version == "calculated_v1"
            mock_calc.assert_called_once()


def test_calculate_static_hash(tmp_path: Path) -> None:
    """Test static hash calculation."""
    # Create dummy static structure
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "style.css").write_text("body { color: red; }")

    # Calculate hash
    hash1 = calculate_static_hash(static_dir)
    assert len(hash1) == 8

    # Modify file
    (static_dir / "style.css").write_text("body { color: blue; }")
    hash2 = calculate_static_hash(static_dir)

    assert hash1 != hash2


def test_calculate_static_hash_missing_dir() -> None:
    """Test hash calculation handles missing directory gracefully."""
    assert calculate_static_hash("nonexistent/path") == "v1"


def test_calculate_static_hash_oserror(tmp_path: Path) -> None:
    """Test that hash calculation ignores files that raise OSError (e.g. permissions)."""
    static_dir = tmp_path / "static_oserror"
    static_dir.mkdir()
    # Create two files: one readable, one "unreadable"
    (static_dir / "readable.css").write_text("content")
    (static_dir / "unreadable.css").write_text("secret")

    # Capture the real Path.open to pass through for the readable file
    original_open = Path.open

    # Added typing to arguments to satisfy mypy [no-untyped-def]
    # FIX: Added specific types for self, args, kwargs
    def side_effect(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Trigger OSError only for the specific unreadable file
        # We check self.name which should exist on the Path object passed as self
        if getattr(self, "name", "") == "unreadable.css":
            raise OSError("Simulated permission error")
        return original_open(self, *args, **kwargs)

    # Patch Path.open to inject the error
    with patch("pathlib.Path.open", side_effect=side_effect, autospec=True):
        # The hash should be calculated based on readable.css only
        # We assume readable.css (alphabetical) or order doesn't matter for this test
        # logic just needs to ensure it doesn't crash.
        h = calculate_static_hash(static_dir)
        assert len(h) == 8


def test_calculate_static_hash_os_error_read(tmp_path: Path) -> None:
    """Test that hash calculation handles OSError during file reading.

    This ensures full coverage for the `except OSError: pass` block in calculate_static_hash,
    specifically when `f.read()` fails.
    """
    static_dir = tmp_path / "static_os_read_error"
    static_dir.mkdir()
    file_path = static_dir / "test.txt"
    file_path.write_text("some content")

    # Mock the file object returned by open
    with patch("pathlib.Path.open") as mock_open:
        mock_file = mock_open.return_value.__enter__.return_value
        # Simulate OSError on read
        mock_file.read.side_effect = OSError("Simulated read error")

        # The function should ignore the error and return a hash (of nothing/empty/other files)
        # Since this is the only file, it might result in a hash of empty or initial state
        # but crucial part is: it must not raise.
        h = calculate_static_hash(static_dir)
        assert isinstance(h, str)
        assert len(h) > 0


def test_sanitize_title_dot_handling() -> None:
    """Refute the PDF claim that '. Hidden Book' results in empty stem.

    The PDF claimed: 'If a user provides a title like . Hidden Book, base_stem becomes an empty string.'
    This test proves that strip('. ') handles it correctly.
    """
    # 1. Leading dot with space
    assert sanitize_title(". Hidden Book") == "Hidden Book"
    # 2. Leading dot no space
    assert sanitize_title(".Hidden Book") == "Hidden Book"
    # 3. Trailing dot
    assert sanitize_title("Hidden Book.") == "Hidden Book"
    # 4. Just dots (should fallback)
    assert sanitize_title("...") == FALLBACK_TITLE


def test_construct_safe_save_path_deep_path_warning(caplog: LogCaptureFixture) -> None:
    """Test that a warning is logged if SAVE_PATH_BASE is deep but valid."""
    # 249 - 235 = 14 (safe, > 10). Wait, warning threshold is < 10.
    # We want a path that triggers warning (limit < 10) but NOT exception (limit >= 5).
    # 249 - x < 10 => x > 239.
    # 249 - x >= 5 => x <= 244.
    # So length 240 is perfect. (249-240 = 9).
    deep_path = "/" + "a" * 239  # +1 slash = 240 chars
    with caplog.at_level(logging.WARNING):
        construct_safe_save_path(deep_path, "Short Title")
    assert "SAVE_PATH_BASE is extremely deep" in caplog.text


def test_construct_safe_save_path_raises_if_too_deep() -> None:
    """Test that ValueError is raised if SAVE_PATH_BASE leaves no room for filename."""
    # Calculated limit = 249 - base_len.
    # We want limit < MIN_FILENAME_LENGTH (5).
    # 249 - x < 5 => x > 244.
    deep_path = "/" + "a" * 245  # 246 chars
    with pytest.raises(ValueError, match="SAVE_PATH_BASE is too deep"):
        construct_safe_save_path(deep_path, "Short Title")


def test_format_size() -> None:
    """Test the format_size utility (human readable bytes)."""
    assert format_size(None) == "Unknown"
    assert format_size("invalid") == "Unknown"
    assert format_size(500) == "500.00 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(1024 * 1024) == "1.00 MB"
    assert format_size(1024 * 1024 * 1024) == "1.00 GB"
    assert format_size("2048") == "2.00 KB"
