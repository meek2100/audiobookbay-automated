"""Tests for the core scraper logic, focusing on flow and extraction."""

from typing import Any, cast
from unittest.mock import patch

from app.scraper import extract_magnet_link
from app.scraper.parser import BookDict


def test_extract_magnet_deduplication(mock_sleep: Any) -> None:
    """Test that duplicate trackers are removed from the magnet link.

    Ensures we don't spam clients with redundant tracker parameters.
    """
    url = "https://audiobookbay.lu/book"
    # Mock details containing duplicate trackers
    mock_details = cast(
        BookDict,
        {
            "info_hash": "abc123hash456",
            "trackers": ["http://tracker.com/announce", "http://tracker.com/announce"],
        },
    )

    with patch("app.scraper.core.get_book_details", return_value=mock_details):
        # Mock global trackers to include duplicates of what's already in the book details
        # plus a unique one.
        with patch(
            "app.scraper.core.get_trackers", return_value=["http://tracker.com/announce", "udp://new.tracker:80"]
        ):
            magnet, error = extract_magnet_link(url)

            assert error is None
            assert magnet is not None

            # Verify "tracker.com" appears only once in the magnet link
            # We check the count of the encoded URL component
            assert magnet.count("tracker.com") == 1
            assert "new.tracker" in magnet
