# File: tests/scraper/test_details.py
"""Tests for get_book_details."""

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import requests

from audiobook_automated.scraper import get_book_details
from audiobook_automated.scraper.parser import BookDetails


def test_get_book_details_sanitization(mock_sleep: Any) -> None:
    """Test strict HTML sanitization in get_book_details."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Sanitized Book</h1></div>
        <div class="desc">
            <p style="color: red;">Allowed P tag.</p>
            <script>alert('XSS');</script>
            <b>Bold Text</b>
            <a href="http://bad.com">Malicious Link</a>
        </div>
    </div>
    """

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/book")

        # Explicitly cast potentially None value to string for 'in' check
        description = str(details.get("description", ""))

        assert "<p>Allowed P tag.</p>" in description
        assert "style" not in description  # Attribute stripped
        assert "<b>Bold Text</b>" in description
        assert "Malicious Link" in description
        assert "<a href" not in description
        assert "<script>" not in description


def test_get_book_details_caching(mock_sleep: Any) -> None:
    """Test that details are returned from cache."""
    url = "https://audiobookbay.lu/cached_details"
    # FIX: Explicit cast for mock cache entry
    expected = cast(BookDetails, {"title": "Cached Details"})
    # Use core import to ensure identity match
    from audiobook_automated.scraper.core import details_cache  # type: ignore[attr-defined]

    details_cache[url] = expected

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session") as mock_session_getter:
        result = get_book_details(url)
        assert result == expected
        mock_session_getter.assert_not_called()


def test_get_book_details_success(details_html: str, mock_sleep: Any) -> None:
    """Test successful parsing of book details from a valid HTML page."""
    # Cache cleared automatically by fixture
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = details_html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/valid-book")

        assert details["title"] == "A Game of Thrones"
        assert details["info_hash"] == "eb154ac7886539c4d01eae14908586e336cdb550"
        assert details["file_size"] == "1.37 GBs"


def test_get_book_details_default_cover_skip(mock_sleep: Any) -> None:
    """Test that if details page has the default cover, it is skipped (None)."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Book Default Cover</h1></div>
        <div class="postContent">
            <img itemprop="image" src="/images/default_cover.jpg">
        </div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/def-cover")
        assert details["cover"] is None


def test_get_book_details_failure(mock_sleep: Any) -> None:
    """Test that RequestExceptions are propagated up from the session."""
    # FIX: Patch get_thread_session as that is what core.py imports/uses
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.RequestException("Net Down")

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        # We now raise RuntimeError with exception chaining
        with pytest.raises(RuntimeError) as exc:
            get_book_details("https://audiobookbay.lu/fail-book")
        assert "Failed to fetch book details" in str(exc.value)


def test_get_book_details_ssrf_protection() -> None:
    """Test that get_book_details rejects non-ABB domains."""
    with pytest.raises(ValueError) as exc:
        get_book_details("https://google.com/admin")
    assert "Invalid domain" in str(exc.value)


def test_get_book_details_empty(mock_sleep: Any) -> None:
    """Test that providing an empty URL string raises a ValueError."""
    with pytest.raises(ValueError) as exc:
        get_book_details("")
    assert "No URL provided" in str(exc.value)


def test_get_book_details_url_parse_error(mock_sleep: Any) -> None:
    """Test that malformed URLs trigger a ValueError."""
    with patch("audiobook_automated.scraper.core.urlparse", side_effect=Exception("Boom")):
        with pytest.raises(ValueError) as exc:
            get_book_details("http://anything")
    assert "Invalid URL format" in str(exc.value)


def test_get_book_details_missing_metadata(mock_sleep: Any) -> None:
    """Test fallback to 'Unknown' when metadata fields are missing from HTML."""
    html = """<div class="post"><div class="postTitle"><h1>Empty Book</h1></div></div>"""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/empty")
        assert details["language"] == "Unknown"
        assert details["format"] == "Unknown"


def test_get_book_details_unknown_bitrate_normalization(mock_sleep: Any) -> None:
    """Test that a bitrate of '?' is normalized to 'Unknown'."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Unknown Bitrate</h1></div>
        <div class="postContent"><p>Bitrate: ?</p></div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/unknown")
        assert details["bitrate"] == "Unknown"


def test_get_book_details_partial_bitrate(mock_sleep: Any) -> None:
    """Test parsing when only the bitrate is present in the format line."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Partial Info</h1></div>
        <div class="postContent"><p>Bitrate: 128 Kbps</p></div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/partial_bitrate")
        assert details["format"] == "Unknown"
        assert details["bitrate"] == "128 Kbps"


def test_get_book_details_partial_format(mock_sleep: Any) -> None:
    """Test parsing when only the format (e.g., MP3) is present."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Partial Info</h1></div>
        <div class="postContent"><p>Format: MP3</p></div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/partial")
        assert details["format"] == "MP3"
        assert details["bitrate"] == "Unknown"


def test_get_book_details_content_without_metadata_labels(mock_sleep: Any) -> None:
    """Test behavior when the content div exists but contains no recognizable labels."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>No Metadata</h1></div>
        <div class="postContent"><p>Just text.</p></div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/no_meta")
        assert details["format"] == "Unknown"


def test_get_book_details_consistency_checks(mock_sleep: Any) -> None:
    """Test that '?' values in detailed metadata are converted to 'Unknown'."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Mystery Details</h1></div>
        <div class="postInfo">Category: ? Language: ?</div>
        <div class="postContent">
            <p>Posted: ?</p>
            <p>Format: ?</p>
            <span class="author" itemprop="author">?</span>
            <span class="narrator" itemprop="author">?</span>
        </div>
        <table class="torrent_info">
            <tr><td>File Size:</td><td>?</td></tr>
        </table>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/mystery")

        assert details["language"] == "Unknown"
        assert details["category"] == ["Unknown"]
        assert details["post_date"] == "Unknown"
        assert details["format"] == "Unknown"
        assert details["author"] == "Unknown"
        assert details["narrator"] == "Unknown"
        assert details["file_size"] == "Unknown"


def test_get_book_details_info_hash_strategy_2(mock_sleep: Any) -> None:
    """Forces Strategy 2: Table structure is broken (no table.torrent_info)."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Strategy 2 Book</h1></div>
        <table>
            <tr>
                <td>Info Hash:</td>
                <td>1111111111222222222233333333334444444444</td>
            </tr>
        </table>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/strat2")
        assert details["info_hash"] == "1111111111222222222233333333334444444444"


def test_get_book_details_info_hash_strategy_3(mock_sleep: Any) -> None:
    """Forces Strategy 3: Regex fallback."""
    html = """
    <div class="post">
        <div class="postTitle"><h1>Strategy 3 Book</h1></div>
        <div class="desc">
            Some text containing the hash 5555555555666666666677777777778888888888 in the body.
        </div>
    </div>
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_session.get.return_value = mock_response

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        details = get_book_details("https://audiobookbay.lu/strat3")
        assert details["info_hash"] == "5555555555666666666677777777778888888888"
