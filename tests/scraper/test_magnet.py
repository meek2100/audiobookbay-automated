# tests/scraper/test_magnet.py
"""Tests for magnet link extraction logic."""

from typing import Any, cast
from unittest.mock import patch

from audiobook_automated.scraper import extract_magnet_link
from audiobook_automated.scraper.parser import BookDetails


def test_extract_magnet_deduplication(mock_sleep: Any) -> None:
    """Test that duplicate trackers are removed from the magnet link.

    Ensures we don't spam clients with redundant tracker parameters.
    """
    url = "https://audiobookbay.lu/book"
    # Mock details containing duplicate trackers
    mock_details = cast(
        BookDetails,
        {
            "info_hash": "abc123hash456",
            "trackers": ["http://tracker.com/announce", "http://tracker.com/announce"],
        },
    )

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        # Patch the correct function 'get_trackers' instead of the non-existent 'CONFIGURED_TRACKERS'
        with patch(
            "audiobook_automated.scraper.core.get_trackers",
            return_value=["http://tracker.com/announce", "udp://new.tracker:80"],
        ):
            magnet, error = extract_magnet_link(url)

            assert error is None
            assert magnet is not None

            # Verify "tracker.com" appears only once in the magnet link
            # We check the count of the encoded URL component
            assert magnet.count("tracker.com") == 1
            assert "new.tracker" in magnet


def test_extract_magnet_success(mock_sleep: Any) -> None:
    """Test successful magnet link extraction."""
    url = "https://audiobookbay.lu/book"
    mock_details = cast(
        BookDetails,
        {"info_hash": "abc123hash456", "trackers": ["http://tracker.com/announce"]},
    )

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        # Patch the function actually used in core.py
        with patch("audiobook_automated.scraper.core.get_trackers", return_value=[]):
            magnet, error = extract_magnet_link(url)
            assert error is None
            assert magnet is not None
            assert "magnet:?xt=urn:btih:abc123hash456" in magnet
            assert "tracker.com" in magnet


def test_extract_magnet_missing_info_hash(mock_sleep: Any) -> None:
    """Test behavior when get_book_details returns Unknown hash."""
    url = "https://audiobookbay.lu/book"
    mock_details = cast(BookDetails, {"info_hash": "Unknown", "trackers": []})

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        magnet, error = extract_magnet_link(url)
        assert magnet is None
        assert error is not None
        assert "Info Hash could not be found" in error


def test_extract_magnet_ssrf_inherited(mock_sleep: Any) -> None:
    """Verifies that extract_magnet_link inherits the SSRF validation from get_book_details."""
    url = "https://google.com/evil"
    # Real logic: get_book_details raises ValueError for invalid domains
    with patch("audiobook_automated.scraper.core.get_book_details", side_effect=ValueError("Invalid domain")):
        magnet, error = extract_magnet_link(url)
        assert magnet is None
        assert error is not None
        assert "Invalid domain" in error


def test_extract_magnet_generic_exception(mock_sleep: Any) -> None:
    """Test handling of generic exceptions during extraction."""
    url = "https://audiobookbay.lu/book"
    with patch("audiobook_automated.scraper.core.get_book_details", side_effect=Exception("Database down")):
        with patch("audiobook_automated.scraper.core.logger") as mock_logger:
            magnet, error = extract_magnet_link(url)
            assert magnet is None
            assert error is not None
            assert "Database down" in error
            assert mock_logger.error.called


def test_extract_magnet_none_trackers(mock_sleep: Any) -> None:
    """Test extract_magnet_link handling when trackers is explicitly None."""
    url = "https://audiobookbay.lu/book"
    mock_details = cast(BookDetails, {"info_hash": "abc123hash", "trackers": None})

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        with patch("audiobook_automated.scraper.core.get_trackers", return_value=[]):
            magnet, error = extract_magnet_link(url)
            assert error is None
            assert magnet is not None
            assert "magnet:?xt=urn:btih:abc123hash" in magnet
            assert "&tr=" not in magnet
