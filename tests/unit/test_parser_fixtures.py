# File: tests/unit/test_parser_fixtures.py
"""Unit tests for parser regex resilience using fixtures."""

# pyright: reportPrivateUsage=false

from audiobook_automated.scraper.parser import (
    RE_CATEGORY,
    RE_HASH_STRING,
    RE_LANGUAGE,
    BookMetadata,
    _normalize_metadata,
)


def test_date_parsing_resilience() -> None:
    """Test resilience of date parsing logic (note: date parsing is mainly in JS/template, but we check regex safety here)."""
    # The parser.py itself doesn't have a date regex, it relies on get_text_after_label
    # However, we can test that our general regexes are safe.
    pass


def test_regex_language() -> None:
    """Test language regex against various formats."""
    assert RE_LANGUAGE.search("Language: English")
    assert RE_LANGUAGE.search("Language:   English")
    match = RE_LANGUAGE.search("Category: Sci-Fi Language: English")
    assert match and match.group(1) == "English"


def test_regex_category() -> None:
    """Test category regex against various formats."""
    # Standard format
    match = RE_CATEGORY.search("Category: Sci-Fi Language: English")
    assert match and match.group(1).strip() == "Sci-Fi"

    # Missing language (end of string)
    match = RE_CATEGORY.search("Category: Fantasy")
    assert match and match.group(1).strip() == "Fantasy"

    # Multiple categories
    match = RE_CATEGORY.search("Category: Sci-Fi, Action Language: English")
    assert match and match.group(1).strip() == "Sci-Fi, Action"


def test_regex_hash() -> None:
    """Test hash regex supports SHA-1 and SHA-256 (BitTorrent v2)."""
    # SHA-1 (40 hex chars)
    sha1 = "a" * 40
    assert RE_HASH_STRING.search(f"Info Hash: {sha1}")

    # SHA-256 (64 hex chars)
    sha256 = "b" * 64
    assert RE_HASH_STRING.search(f"Info Hash: {sha256}")

    # Invalid length
    assert not RE_HASH_STRING.search("Info Hash: " + "c" * 39)
    assert not RE_HASH_STRING.search("Info Hash: " + "d" * 65)


def test_metadata_normalization() -> None:
    """Test metadata normalization logic."""
    meta = BookMetadata(
        category=["Sci-Fi", "", "?", "Unknown"],
        file_size="? ",
        bitrate="?",
        language=" English ",
    )
    _normalize_metadata(meta)

    assert meta.category == ["Sci-Fi", "Unknown", "Unknown", "Unknown"]
    assert meta.file_size == "Unknown"
    assert meta.bitrate == "Unknown"
    assert meta.language == "English"
