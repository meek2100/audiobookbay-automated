import logging
import re
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import requests
import requests_mock
from bs4 import BeautifulSoup, Tag

from audiobook_automated.scraper import extract_magnet_link, fetch_and_parse_page, get_book_details
from audiobook_automated.scraper.parser import (
    BookDict,
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


# --- Integration Tests: Fetch and Parse Page (Regression Testing) ---


def test_fetch_and_parse_page_real_structure(real_world_html: str, mock_sleep: Any) -> None:
    hostname = "audiobookbay.lu"
    query = "test"
    page = 1
    user_agent = "TestAgent/1.0"

    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=real_world_html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page(hostname, query, page, user_agent, 30)

    assert mock_sleep.called
    assert len(results) == 1
    book = results[0]
    assert "A Game of Thrones" in book["title"]
    assert book["language"] == "English"
    assert book["format"] == "M4B"
    assert book["file_size"] == "1.37 GBs"


def test_fetch_and_parse_page_unknown_bitrate() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">Test</a></h2></div>
        <div class="postContent">
            <p>Posted: 01 Jan 2024<br>Bitrate: ?</p>
        </div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["bitrate"] == "Unknown"


def test_fetch_and_parse_page_malformed() -> None:
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text="<html><body></body></html>", status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results == []


def test_fetch_and_parse_page_zero_results(mock_sleep: Any) -> None:
    """Test that a valid page with no posts returns an empty list without error."""
    html = """
    <html>
        <body>
            <div id="content">
                <p>No results found for "nonexistent".</p>
            </div>
        </body>
    </html>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=nonexistent", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "nonexistent", 1, "ua", 30)
    assert results == []


def test_fetch_and_parse_page_mixed_validity() -> None:
    mixed_html = """
    <div class="post"><div>Broken Info</div></div>
    <div class="post">
        <div class="postTitle"><h2><a href="/valid">Valid Book</a></h2></div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=mixed_html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert len(results) == 1
    assert results[0]["title"] == "Valid Book"


def test_parsing_structure_change() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postContent"><p>Random text.</p></div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["format"] == "Unknown"


def test_fetch_and_parse_page_language_fallback() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postInfo">Languages: English</div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["language"] == "Unknown"


def test_fetch_and_parse_page_missing_regex_matches() -> None:
    """Tests the scenario where postInfo exists but regexes fail to find Category or Language."""
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postInfo">No recognizable labels here</div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["language"] == "Unknown"
    assert results[0]["category"] == "Unknown"


def test_fetch_and_parse_page_no_posted_date() -> None:
    """Test when the 'Posted:' label is missing from the content paragraphs."""
    hostname = "audiobookbay.lu"
    query = "no_posted"
    html = """
    <div class="post">
        <div class="postTitle">
            <h2><a href="/abss/test/">Title</a></h2>
        </div>
        <div class="postContent">
            <p>Some description text without the date.</p>
            <p>Format: MP3</p>
        </div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/1/?s={query}", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page(hostname, query, 1, "UA", 30)

    assert len(results) == 1
    assert results[0]["post_date"] == "Unknown"
    assert results[0]["format"] == "MP3"


def test_fetch_and_parse_page_missing_title() -> None:
    hostname = "audiobookbay.lu"
    query = "no_title"
    html = """
    <div class="post">
        <div class="postContent"><p>Content but no title</p></div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/1/?s={query}", text=html, status_code=200)

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page(hostname, query, 1, "UA", 30)
    assert results == []


def test_fetch_page_post_exception(caplog: Any) -> None:
    mock_session = MagicMock()
    mock_session.get.return_value.text = "<html></html>"
    mock_session.get.return_value.status_code = 200

    mock_post = MagicMock()
    mock_post.select_one.side_effect = Exception("Post Error")

    # Patch BeautifulSoup in app.scraper.core where it is imported
    with patch("audiobook_automated.scraper.core.BeautifulSoup") as mock_bs:
        mock_bs.return_value.select.return_value = [mock_post]
        with caplog.at_level(logging.ERROR):
            # FIX: Patch get_thread_session as that is what core.py imports/uses
            with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
                results = fetch_and_parse_page("host", "q", 1, "ua", 30)
            assert results == []
            assert "Could not process post" in caplog.text


def test_fetch_page_urljoin_exception(real_world_html: str) -> None:
    mock_session = MagicMock()
    mock_session.get.return_value.text = real_world_html
    mock_session.get.return_value.status_code = 200

    # Patch urljoin in app.scraper.core where it is imported
    with patch("audiobook_automated.scraper.core.urljoin", side_effect=Exception("Join Error")):
        # FIX: Patch get_thread_session as that is what core.py imports/uses
        with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results == []


def test_fetch_and_parse_page_missing_cover_image() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Cover</a></h2></div>
    </div>
    """
    mock_session = requests.Session()
    with patch.object(mock_session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        # FIX: Patch get_thread_session as that is what core.py imports/uses
        with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    # Expect None so UI handles versioning
    assert results[0]["cover"] is None


def test_fetch_and_parse_page_missing_post_info() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Info</a></h2></div>
    </div>
    """
    mock_session = requests.Session()
    with patch.object(mock_session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        # FIX: Patch get_thread_session as that is what core.py imports/uses
        with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["language"] == "Unknown"


def test_fetch_and_parse_page_remote_default_cover_optimization() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">Remote Default</a></h2></div>
        <div class="postContent">
            <img src="/images/default_cover.jpg" alt="Cover">
            <p>Posted: 01 Jan 2024</p>
        </div>
    </div>
    """
    mock_session = requests.Session()
    with patch.object(mock_session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        # FIX: Patch get_thread_session as that is what core.py imports/uses
        with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    # Assert it was converted to None
    assert results[0]["cover"] is None


# --- Get Book Details Tests ---


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
    expected = cast(BookDict, {"title": "Cached Details"})
    # FIX: Use the new details_cache instead of search_cache (which stores lists)
    # The cache is imported from scraper.core (which gets it from network)
    from audiobook_automated.scraper.core import details_cache

    details_cache[url] = expected

    # FIX: Patch get_thread_session as that is what core.py imports/uses
    with patch("audiobook_automated.scraper.core.get_thread_session") as mock_session_getter:
        result = get_book_details(url)
        assert result == expected
        mock_session_getter.assert_not_called()


def test_get_book_details_success(details_html: str, mock_sleep: Any) -> None:
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
    # FIX: Patch get_thread_session as that is what core.py imports/uses
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.RequestException("Net Down")

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        with pytest.raises(requests.exceptions.RequestException):
            get_book_details("https://audiobookbay.lu/fail-book")


def test_get_book_details_ssrf_protection() -> None:
    """Test that get_book_details rejects non-ABB domains."""
    with pytest.raises(ValueError) as exc:
        get_book_details("https://google.com/admin")
    assert "Invalid domain" in str(exc.value)


def test_get_book_details_empty(mock_sleep: Any) -> None:
    with pytest.raises(ValueError) as exc:
        get_book_details("")
    assert "No URL provided" in str(exc.value)


def test_get_book_details_url_parse_error(mock_sleep: Any) -> None:
    with patch("audiobook_automated.scraper.core.urlparse", side_effect=Exception("Boom")):
        with pytest.raises(ValueError) as exc:
            get_book_details("http://anything")
    assert "Invalid URL format" in str(exc.value)


def test_get_book_details_missing_metadata(mock_sleep: Any) -> None:
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
        assert details["category"] == "Unknown"
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


# --- Extract Magnet Link Tests ---


def test_extract_magnet_success(mock_sleep: Any) -> None:
    url = "https://audiobookbay.lu/book"
    # Mock return from get_book_details
    mock_details = cast(BookDict, {"info_hash": "abc123hash456", "trackers": ["http://tracker.com/announce"]})

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        # FIX: Patch the get_trackers function instead of the removed global
        with patch("audiobook_automated.scraper.core.get_trackers", return_value=[]):
            magnet, error = extract_magnet_link(url)
            assert error is None
            assert magnet is not None
            assert "magnet:?xt=urn:btih:abc123hash456" in magnet
            assert "tracker.com" in magnet


def test_extract_magnet_missing_info_hash(mock_sleep: Any) -> None:
    """Test behavior when get_book_details returns Unknown hash."""
    url = "https://audiobookbay.lu/book"
    mock_details = cast(BookDict, {"info_hash": "Unknown", "trackers": []})

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
    # Mock details where 'trackers' key exists but value is None
    # We cast to avoid MyPy errors, simulating runtime data that might violate TypedDict if not careful
    mock_details = cast(BookDict, {"info_hash": "abc123hash", "trackers": None})

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        # Patch get_trackers to return empty list
        with patch("audiobook_automated.scraper.core.get_trackers", return_value=[]):
            magnet, error = extract_magnet_link(url)

            assert error is None
            assert magnet is not None
            assert "magnet:?xt=urn:btih:abc123hash" in magnet
            # Should not contain any tr= parameters if configured trackers are also empty
            assert "&tr=" not in magnet
