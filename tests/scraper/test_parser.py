import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
import requests_mock
from bs4 import BeautifulSoup

from app.scraper import extract_magnet_link, fetch_and_parse_page, get_book_details
from app.scraper.parser import get_text_after_label, parse_post_content

# --- Unit Tests: Helper Functions ---


def test_get_text_after_label_valid() -> None:
    html = "<div><p>Format: <span>MP3</span></p></div>"
    soup = BeautifulSoup(html, "html.parser")
    p_tag = soup.find("p")
    res = get_text_after_label(p_tag, "Format:")
    assert res == "MP3"


def test_get_text_after_label_inline() -> None:
    html = "<div><p>Posted: 10 Jan 2020</p></div>"
    soup = BeautifulSoup(html, "html.parser")
    p_tag = soup.find("p")
    res = get_text_after_label(p_tag, "Posted:")
    assert res == "10 Jan 2020"


def test_get_text_after_label_exception() -> None:
    """Test that exceptions during parsing are handled gracefully."""
    mock_container = MagicMock()
    # Force an exception when .find() is called
    mock_container.find.side_effect = Exception("BS4 Internal Error")
    result = get_text_after_label(mock_container, "Label:")
    assert result == "Unknown"


def test_get_text_after_label_fallback() -> None:
    """Test that it returns 'Unknown' if label exists but no value follows."""

    class FakeNavigableString(str):
        def find_next_sibling(self) -> Any:
            return None

    mock_container = MagicMock()
    mock_label_node = FakeNavigableString("Format:")
    mock_container.find.return_value = mock_label_node

    result = get_text_after_label(mock_container, "Format:")
    assert result == "Unknown"


def test_get_text_after_label_not_found() -> None:
    """Test that it returns 'Unknown' if the label text is not found in the container."""
    html = "<div><p>Some other content</p></div>"
    soup = BeautifulSoup(html, "html.parser")
    # 'Format:' does not exist in the HTML
    result = get_text_after_label(soup, "Format:")
    assert result == "Unknown"


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
    soup_info = BeautifulSoup(html_info, "html.parser").find("div")
    soup_content = BeautifulSoup(html_content, "html.parser").find("div")

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
    soup_content = BeautifulSoup(html_content, "html.parser").find("div")
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
    soup_info = BeautifulSoup(html_info, "html.parser").find("div")
    soup_content = BeautifulSoup(html_content, "html.parser").find("div")

    meta = parse_post_content(soup_content, soup_info)

    assert meta.category == "Unknown"
    assert meta.language == "Unknown"  # Was empty/whitespace
    assert meta.format == "Unknown"  # Was ?
    assert meta.bitrate == "Unknown"  # Was empty


# --- Integration Tests: Fetch and Parse Page (Regression Testing) ---


def test_fetch_and_parse_page_real_structure(real_world_html: str, mock_sleep: Any) -> None:
    hostname = "audiobookbay.lu"
    query = "test"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=real_world_html, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)

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
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert results[0]["bitrate"] == "Unknown"


def test_fetch_and_parse_page_malformed() -> None:
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text="<html><body></body></html>", status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
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
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=nonexistent", text=html, status_code=200)

    results = fetch_and_parse_page(session, "host", "nonexistent", 1, "ua")
    assert results == []


def test_fetch_and_parse_page_mixed_validity() -> None:
    mixed_html = """
    <div class="post"><div>Broken Info</div></div>
    <div class="post">
        <div class="postTitle"><h2><a href="/valid">Valid Book</a></h2></div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=mixed_html, status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert len(results) == 1
    assert results[0]["title"] == "Valid Book"


def test_parsing_structure_change() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postContent"><p>Random text.</p></div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert results[0]["format"] == "Unknown"


def test_fetch_and_parse_page_language_fallback() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postInfo">Languages: English</div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert results[0]["language"] == "Unknown"


def test_fetch_and_parse_page_missing_regex_matches() -> None:
    """Tests the scenario where postInfo exists but regexes fail to find Category or Language."""
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postInfo">No recognizable labels here</div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
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
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/1/?s={query}", text=html, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, 1, "UA")

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
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/1/?s={query}", text=html, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, 1, "UA")
    assert results == []


def test_fetch_page_post_exception(caplog: Any) -> None:
    session = MagicMock()
    session.get.return_value.text = "<html></html>"
    session.get.return_value.status_code = 200

    mock_post = MagicMock()
    mock_post.select_one.side_effect = Exception("Post Error")

    # Patch BeautifulSoup in app.scraper.core where it is imported
    with patch("app.scraper.core.BeautifulSoup") as mock_bs:
        mock_bs.return_value.select.return_value = [mock_post]
        with caplog.at_level(logging.ERROR):
            results = fetch_and_parse_page(session, "host", "q", 1, "ua")
            assert results == []
            assert "Could not process post" in caplog.text


def test_fetch_page_urljoin_exception(real_world_html: str) -> None:
    session = MagicMock()
    session.get.return_value.text = real_world_html
    session.get.return_value.status_code = 200

    # Patch urljoin in app.scraper.core where it is imported
    with patch("app.scraper.core.urljoin", side_effect=Exception("Join Error")):
        results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert results == []


def test_fetch_and_parse_page_missing_cover_image() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Cover</a></h2></div>
    </div>
    """
    session = requests.Session()
    with patch.object(session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    # Expect None so UI handles versioning
    assert results[0]["cover"] is None


def test_fetch_and_parse_page_missing_post_info() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Info</a></h2></div>
    </div>
    """
    session = requests.Session()
    with patch.object(session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        results = fetch_and_parse_page(session, "host", "q", 1, "ua")
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
    session = requests.Session()
    with patch.object(session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        results = fetch_and_parse_page(session, "host", "q", 1, "ua")
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

    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/book")

        # Explicitly cast potentially None value to string for 'in' check
        description = str(details.get("description", ""))

        assert "<p>Allowed P tag.</p>" in description
        assert "style" not in description  # Attribute stripped
        assert "<b>Bold Text</b>" in description
        assert "Malicious Link" in description
        assert "<a href" not in description
        assert "<script>" not in description


def test_get_book_details_success(details_html: str, mock_sleep: Any) -> None:
    # Cache cleared automatically by fixture
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = details_html
        mock_get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/valid-book")

        assert details["title"] == "A Game of Thrones"
        assert details["info_hash"] == "eb154ac7886539c4d01eae14908586e336cdb550"
        assert details["file_size"] == "1.37 GBs"
        assert details["language"] == "English"
        assert details["category"] == "Fantasy"
        assert details["post_date"] == "10 Jan 2024"


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
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/def-cover")
        assert details["cover"] is None


def test_get_book_details_failure(mock_sleep: Any) -> None:
    with patch("requests.Session.get", side_effect=requests.exceptions.RequestException("Net Down")):
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
    with patch("app.scraper.core.urlparse", side_effect=Exception("Boom")):
        with pytest.raises(ValueError) as exc:
            get_book_details("http://anything")
    assert "Invalid URL format" in str(exc.value)


def test_get_book_details_missing_metadata(mock_sleep: Any) -> None:
    html = """<div class="post"><div class="postTitle"><h1>Empty Book</h1></div></div>"""
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
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
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        details = get_book_details("https://audiobookbay.lu/unknown")
        assert details["bitrate"] == "Unknown"


def test_get_book_details_partial_bitrate(mock_sleep: Any) -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h1>Partial Info</h1></div>
        <div class="postContent"><p>Bitrate: 128 Kbps</p></div>
    </div>
    """
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
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
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
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
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
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
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response

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
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response

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
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/strat3")
        assert details["info_hash"] == "5555555555666666666677777777778888888888"


# --- Extract Magnet Link Tests ---


def test_extract_magnet_success(mock_sleep: Any) -> None:
    url = "https://audiobookbay.lu/book"
    mock_details = {"info_hash": "abc123hash456", "trackers": ["http://tracker.com/announce"]}

    with patch("app.scraper.core.get_book_details", return_value=mock_details):
        with patch("app.scraper.core.CONFIGURED_TRACKERS", []):
            magnet, error = extract_magnet_link(url)
            assert error is None
            assert magnet is not None
            assert "magnet:?xt=urn:btih:abc123hash456" in magnet
            assert "tracker.com" in magnet


def test_extract_magnet_missing_info_hash(mock_sleep: Any) -> None:
    url = "https://audiobookbay.lu/book"
    mock_details = {"info_hash": "Unknown", "trackers": []}

    with patch("app.scraper.core.get_book_details", return_value=mock_details):
        magnet, error = extract_magnet_link(url)
        assert magnet is None
        assert error is not None
        assert "Info Hash could not be found" in error


def test_extract_magnet_ssrf_inherited(mock_sleep: Any) -> None:
    url = "https://google.com/evil"
    with patch("app.scraper.core.get_book_details", side_effect=ValueError("Invalid domain")):
        magnet, error = extract_magnet_link(url)
        assert magnet is None
        assert error is not None
        assert "Invalid domain" in error


def test_extract_magnet_generic_exception(mock_sleep: Any) -> None:
    url = "https://audiobookbay.lu/book"
    with patch("app.scraper.core.get_book_details", side_effect=Exception("Database down")):
        with patch("app.scraper.core.logger") as mock_logger:
            magnet, error = extract_magnet_link(url)
            assert magnet is None
            assert error is not None
            assert "Database down" in error
            assert mock_logger.error.called
