# tests/unit/test_utils.py
"""Unit tests for utility functions."""

from pathlib import Path
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
