"""Unit tests for the centralized details parser."""

from bs4 import BeautifulSoup

from app.scraper.parser import parse_book_details

# --- HTML Fixtures ---

HTML_STANDARD = """
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
    soup = BeautifulSoup(HTML_STANDARD, "lxml")
    result = parse_book_details(soup, "http://test.com/book")

    assert result["title"] == "Valid Book Title"
    assert result["info_hash"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert result["file_size"] == "1.2 GB"
    assert result["author"] == "Isaac Asimov"
    assert "udp://tracker.opentrackr.org:1337" in result["trackers"]  # type: ignore[operator]

    # Check Description Sanitization
    assert "<script>" not in result["description"]  # type: ignore[operator]
    assert 'style="color:red"' not in result["description"]  # type: ignore[operator]
    assert "<p>Description line 1.</p>" in result["description"]  # type: ignore[operator]


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


def test_normalize_cover_url() -> None:
    """Test cover URL normalization."""
    # This logic is integrated into parse_book_details, verifying integration
    soup = BeautifulSoup(HTML_STANDARD, "lxml")
    result = parse_book_details(soup, "http://base.com/page/")
    assert result["cover"] == "http://base.com/images/cover.jpg"


def test_missing_elements_robustness() -> None:
    """Test robustness against missing elements (title, content, etc)."""
    minimal_html = "<html><body>Nothing here</body></html>"
    soup = BeautifulSoup(minimal_html, "lxml")
    result = parse_book_details(soup, "http://test.com")

    assert result["title"] == "Unknown Title"
    assert result["info_hash"] == "Unknown"
    assert result["description"] == "No description available."
    assert result["language"] == "Unknown"
