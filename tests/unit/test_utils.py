# File: tests/unit/test_utils.py
"""Unit tests for utility functions."""

from audiobook_automated.constants import (
    FALLBACK_TITLE,
    SAFE_SUFFIX,
    WINDOWS_RESERVED_NAMES,
)
from audiobook_automated.utils import ensure_collision_safety, sanitize_title

# --- Unit Tests for sanitize_title ---


def test_sanitize_title_basic() -> None:
    """Test basic sanitization of illegal characters."""
    assert sanitize_title("Valid Title") == "Valid Title"
    assert sanitize_title("In:val/id*Ti?tle") == "InvalidTitle"
    assert sanitize_title("   Spaces   ") == "Spaces"
    assert sanitize_title("Title.") == "Title"


def test_sanitize_title_empty() -> None:
    """Test empty or whitespace-only inputs return fallback."""
    assert sanitize_title(None) == FALLBACK_TITLE
    assert sanitize_title("") == FALLBACK_TITLE
    assert sanitize_title("   ") == FALLBACK_TITLE
    assert sanitize_title("???") == FALLBACK_TITLE


def test_sanitize_title_windows_reserved() -> None:
    """Test Windows reserved filenames are detected and suffixed."""
    for name in WINDOWS_RESERVED_NAMES:
        # Test exact match
        assert sanitize_title(name).endswith(SAFE_SUFFIX)
        # Test case insensitivity
        assert sanitize_title(name.lower()).endswith(SAFE_SUFFIX)
        # Test with extension
        assert sanitize_title(f"{name}.txt").endswith(SAFE_SUFFIX)


def test_sanitize_title_com_lpt_dynamic() -> None:
    """Test dynamic COM/LPT ranges (COM1-9, LPT1-9)."""
    assert sanitize_title("COM1").endswith(SAFE_SUFFIX)
    assert sanitize_title("LPT9.txt").endswith(SAFE_SUFFIX)
    assert sanitize_title("com5").endswith(SAFE_SUFFIX)
    # Ensure invalid ones (COM0, LPT10) are NOT treated as reserved unless in list
    # (Assuming constants list is standard. LPT10 is generally valid on Windows, unlike LPT1)
    assert not sanitize_title("COM0").endswith(SAFE_SUFFIX)


# --- Unit Tests for ensure_collision_safety ---


def test_ensure_collision_safety_no_change() -> None:
    """Test safe inputs are unchanged."""
    assert ensure_collision_safety("Safe_Title", 240) == "Safe_Title"


def test_ensure_collision_safety_fallback_collision() -> None:
    """Test collision logic triggers on FALLBACK_TITLE."""
    result = ensure_collision_safety(FALLBACK_TITLE, 240)
    assert result != FALLBACK_TITLE
    assert "_" in result
    assert len(result) <= 240


def test_ensure_collision_safety_reserved_collision() -> None:
    """Test collision logic triggers on suffixed reserved names."""
    reserved = "CON" + SAFE_SUFFIX
    result = ensure_collision_safety(reserved, 240)
    assert result != reserved
    assert "_" in result


def test_ensure_collision_safety_length_truncation() -> None:
    """Test truncation when exceeding max_length."""
    long_title = "A" * 50
    result = ensure_collision_safety(long_title, max_length=20)
    assert len(result) <= 20
    assert "_" in result
    # Check truncation happened: 20 - 9 = 11 chars of title + _ + 8 chars of uuid
    assert result.startswith("A" * 11 + "_")


def test_ensure_collision_safety_short_limit() -> None:
    """Test strict length safety with very small limits."""
    # Limit < 9, should return random hex string of that length
    result = ensure_collision_safety("AnyTitle", max_length=5)
    assert len(result) == 5
    # Should not contain original title because it can't fit with separator
    assert result != "AnyTitle"


def test_ensure_collision_safety_min_uuid_limit() -> None:
    """Test edge case where limit is exactly enough for UUID + 1 char."""
    # 9 chars needed for UUID+sep. If limit is 10, we get 1 char title + 9 suffix.
    # Input must be > 10 chars to force truncation.
    result = ensure_collision_safety("LongTitleForTest", max_length=10)
    assert len(result) == 10
    assert result[1] == "_"
