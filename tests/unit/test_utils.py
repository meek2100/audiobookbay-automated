"""Unit tests for utility functions."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from audiobook_automated.constants import FALLBACK_TITLE, SAFE_SUFFIX
from audiobook_automated.utils import calculate_static_hash, ensure_collision_safety, sanitize_title


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
