import re
from typing import Any
from unittest.mock import MagicMock

from bs4 import BeautifulSoup, Tag

from audiobook_automated.scraper.parser import (
    get_text_after_label,
    normalize_cover_url,
    parse_book_details,
    parse_post_content,
)

# --- Unit Tests: Helper Functions ---


def test_get_text_after_label_valid() -> None:
    html = "<div><p>Format: <span>MP3</span></p></div>"
    soup = BeautifulSoup(html, "lxml")
    p_tag = soup.find("p")
    # FIX: Ensure p_tag is treated as a Tag for MyPy safety
    assert isinstance(p_tag, Tag)
    res = get_text_after_label(p_tag, re.compile("Format:"))
    assert res == "MP3"


def test_get_text_after_label_inline() -> None:
    html = "<div><p>Posted: 10 Jan 2020</p></div>"
    soup = BeautifulSoup(html, "lxml")
    p_tag = soup.find("p")
    assert isinstance(p_tag, Tag)
    res = get_text_after_label(p_tag, re.compile("Posted:"))
    assert res == "10 Jan 2020"


def test_get_text_after_label_split_unit() -> None:
    """Test the specific branch where File Size unit is in the next sibling node.

    This covers the 'val += f" {unit_node.strip()}"' logic in parser.py.
    """
    html = "<div><p>File Size: <span>1.5</span> GB</p></div>"
    soup = BeautifulSoup(html, "lxml")
    p_tag = soup.find("p")
    assert isinstance(p_tag, Tag)
    # Note: We must explicitly pass is_file_size=True to trigger the unit concatenation logic
    res = get_text_after_label(p_tag, re.compile("File Size:"), is_file_size=True)
    assert res == "1.5 GB"


def test_get_text_after_label_exception() -> None:
    """Test that exceptions during parsing are handled gracefully."""
    mock_container = MagicMock(spec=Tag)
    # Force an exception when .find() is called
    mock_container.find.side_effect = Exception("BS4 Internal Error")
    result = get_text_after_label(mock_container, re.compile("Label:"))
    assert result == "Unknown"


def test_get_text_after_label_fallback() -> None:
    """Test that it returns 'Unknown' if label exists but no value follows."""

    class FakeNavigableString(str):
        def find_next_sibling(self) -> Any:
            return None

    mock_container = MagicMock(spec=Tag)
    mock_label_node = FakeNavigableString("Format:")
    mock_container.find.return_value = mock_label_node

    result = get_text_after_label(mock_container, re.compile("Format:"))
    assert result == "Unknown"


def test_get_text_after_label_not_found() -> None:
    """Test that it returns 'Unknown' if the label text is not found in the container."""
    html = "<div><p>Some other content</p></div>"
    soup = BeautifulSoup(html, "lxml")
    # 'Format:' does not exist in the HTML (pass soup which is Tag-like)
    result = get_text_after_label(soup, re.compile("Format:"))
    assert result == "Unknown"


def test_normalize_cover_url_valid() -> None:
    """Test valid cover URL normalization."""
    base = "https://audiobookbay.lu/page/1"
    url = normalize_cover_url(base, "/images/book.jpg")
    assert url == "https://audiobookbay.lu/images/book.jpg"


def test_normalize_cover_url_default() -> None:
    """Test that default cover image returns None (optimization)."""
    base = "https://audiobookbay.lu/page/1"
    url = normalize_cover_url(base, "/images/default_cover.jpg")
    assert url is None


def test_normalize_cover_url_empty() -> None:
    """Test that empty relative_url returns None (Lines 116-117 coverage)."""
    assert normalize_cover_url("http://base.com", "") is None


# --- Unit Tests: parse_post_content (Centralized Logic) ---


def test_parse_post_content_full_validity() -> None:
    """Test parsing a fully populated post content and info section."""
    html_info = """
    <div class="postInfo">
        Category: Fantasy Language: English
    </div>
    """
    html_content = """
    <div class="postContent">
        <p>Format: MP3</p>
        <p>Bitrate: 128 Kbps</p>
        <p>Posted: 01 Jan 2024</p>
        <p>File Size: 500 MBs</p>
    </div>
    """
    soup_info = BeautifulSoup(html_info, "lxml").find("div")
    soup_content = BeautifulSoup(html_content, "lxml").find("div")

    # Cast to Tag to satisfy strict typing
    assert isinstance(soup_info, Tag)
    assert isinstance(soup_content, Tag)

    meta = parse_post_content(soup_content, soup_info)

    assert meta.category == "Fantasy"
    assert meta.language == "English"
    assert meta.format == "MP3"
    assert meta.bitrate == "128 Kbps"
    assert meta.post_date == "01 Jan 2024"
    assert meta.file_size == "500 MBs"


def test_parse_post_content_missing_elements() -> None:
    """Test robustness when input divs are None."""
    # Both None
    meta = parse_post_content(None, None)
    assert meta.language == "Unknown"
    assert meta.file_size == "Unknown"

    # One None
    html_content = """<div class="postContent"><p>Format: M4B</p></div>"""
    soup_content = BeautifulSoup(html_content, "lxml").find("div")
    assert isinstance(soup_content, Tag)
    meta = parse_post_content(soup_content, None)

    assert meta.format == "M4B"
    assert meta.category == "Unknown"


def test_parse_post_content_normalization() -> None:
    """Test that '?' and empty strings are normalized to 'Unknown'."""
    html_info = """<div class="postInfo">Category: ? Language:   </div>"""
    html_content = """
    <div class="postContent">
        <p>Format: ?</p>
        <p>Bitrate: </p> </div>
    """
    soup_info = BeautifulSoup(html_info, "lxml").find("div")
    soup_content = BeautifulSoup(html_content, "lxml").find("div")

    assert isinstance(soup_info, Tag)
    assert isinstance(soup_content, Tag)

    meta = parse_post_content(soup_content, soup_info)

    assert meta.category == "Unknown"
    assert meta.language == "Unknown"  # Was empty/whitespace
    assert meta.format == "Unknown"  # Was ?
    assert meta.bitrate == "Unknown"  # Was empty


# --- Unit Tests: parse_book_details (Centralized Logic) ---

HTML_STANDARD_DETAILS = """
<div class="post">
    <div class="postTitle"><h1>Valid Book Title</h1></div>
    <div class="postContent">
        <img itemprop="image" src="/images/cover.jpg" />
        <div class="desc">
            <p>Description line 1.</p>
            <script>alert('xss')</script>
            <span style="color:red">Description line 2.</span>
        </div>
        <p>Posted: 01 Jan 2024</p>
        <p>Format: MP3</p>
    </div>
    <div class="postInfo">Category: Sci-Fi Language: English</div>
    <span class="author" itemprop="author">Isaac Asimov</span>
    <span class="narrator" itemprop="author">John Doe</span>
    <table class="torrent_info">
        <tr><td>Tracker:</td><td>udp://tracker.opentrackr.org:1337</td></tr>
        <tr><td>Info Hash:</td><td>aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</td></tr>
        <tr><td>File Size:</td><td>1.2 GB</td></tr>
    </table>
</div>
"""

HTML_MISSING_HASH_TABLE = """
<div class="post">
    <div class="postTitle"><h1>No Hash Table</h1></div>
    <div class="postContent">Content</div>
    <table>
        <tr><td>Info Hash</td><td>bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb</td></tr>
    </table>
</div>
"""

HTML_REGEX_FALLBACK = """
<div class="post">
    <div class="postTitle"><h1>Regex Fallback</h1></div>
    <div class="postContent">
        Some content with hash embedded: cccccccccccccccccccccccccccccccccccccccc
    </div>
</div>
"""


def test_parse_standard_details() -> None:
    """Test standard details page parsing including trackers and sanitization."""
    soup = BeautifulSoup(HTML_STANDARD_DETAILS, "lxml")
    result = parse_book_details(soup, "http://test.com/book")

    assert result["title"] == "Valid Book Title"
    assert result["info_hash"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert result["file_size"] == "1.2 GB"
    assert result["author"] == "Isaac Asimov"
    assert "udp://tracker.opentrackr.org:1337" in result["trackers"]

    # Check Description Sanitization
    assert "<script>" not in result["description"]
    assert 'style="color:red"' not in result["description"]
    assert "<p>Description line 1.</p>" in result["description"]


def test_parse_fallback_hash_footer() -> None:
    """Test info hash extraction from footer when missing from table."""
    soup = BeautifulSoup(HTML_MISSING_HASH_TABLE, "lxml")
    result = parse_book_details(soup, "http://test.com/book")
    assert result["info_hash"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_parse_fallback_hash_regex() -> None:
    """Test info hash extraction via regex when missing from DOM."""
    soup = BeautifulSoup(HTML_REGEX_FALLBACK, "lxml")
    result = parse_book_details(soup, "http://test.com/book")
    assert result["info_hash"] == "cccccccccccccccccccccccccccccccccccccccc"


def test_parse_book_details_cover_normalization() -> None:
    """Test cover URL normalization integration within parse_book_details."""
    soup = BeautifulSoup(HTML_STANDARD_DETAILS, "lxml")
    result = parse_book_details(soup, "http://base.com/page/")
    assert result["cover"] == "http://base.com/images/cover.jpg"


def test_parse_book_details_robustness() -> None:
    """Test robustness against missing elements (title, content, etc)."""
    minimal_html = "<html><body>Nothing here</body></html>"
    soup = BeautifulSoup(minimal_html, "lxml")
    result = parse_book_details(soup, "http://test.com")

    assert result["title"] == "Unknown Title"
    assert result["info_hash"] == "Unknown"
    assert result["description"] == "No description available."
    assert result["language"] == "Unknown"
