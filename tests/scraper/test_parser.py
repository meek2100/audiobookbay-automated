import logging
from unittest.mock import MagicMock, patch

import pytest
import requests
import requests_mock
from bs4 import BeautifulSoup

from app.scraper import fetch_and_parse_page, get_book_details, get_text_after_label

# --- Unit Tests: Helper Functions ---


def test_get_text_after_label_valid():
    html = "<div><p>Format: <span>MP3</span></p></div>"
    soup = BeautifulSoup(html, "html.parser")
    p_tag = soup.find("p")
    res = get_text_after_label(p_tag, "Format:")
    assert res == "MP3"


def test_get_text_after_label_inline():
    html = "<div><p>Posted: 10 Jan 2020</p></div>"
    soup = BeautifulSoup(html, "html.parser")
    p_tag = soup.find("p")
    res = get_text_after_label(p_tag, "Posted:")
    assert res == "10 Jan 2020"


def test_get_text_after_label_exception():
    """Test that exceptions during parsing are handled gracefully."""
    mock_container = MagicMock()
    # Force an exception when .find() is called
    mock_container.find.side_effect = Exception("BS4 Internal Error")
    result = get_text_after_label(mock_container, "Label:")
    assert result == "Unknown"


def test_get_text_after_label_fallback():
    """Test that it returns 'Unknown' if label exists but no value follows."""

    class FakeNavigableString(str):
        def find_next_sibling(self):
            return None

    mock_container = MagicMock()
    mock_label_node = FakeNavigableString("Format:")
    mock_container.find.return_value = mock_label_node

    result = get_text_after_label(mock_container, "Format:")
    assert result == "Unknown"


# --- Integration Tests: Fetch and Parse Page ---


def test_fetch_and_parse_page_real_structure(real_world_html, mock_sleep):
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


def test_fetch_and_parse_page_unknown_bitrate():
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


def test_fetch_and_parse_page_malformed():
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text="<html><body></body></html>", status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert results == []


def test_fetch_and_parse_page_mixed_validity():
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


def test_parsing_structure_change():
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


def test_fetch_and_parse_page_language_fallback():
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


def test_fetch_and_parse_page_missing_regex_matches():
    """
    Tests the scenario where postInfo exists but regexes fail to find Category or Language.
    This ensures branches for 'if lang_match:' and 'if cat_match:' are fully covered.
    """
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


def test_fetch_and_parse_page_no_posted_date():
    """
    Test when the 'Posted:' label is missing from the content paragraphs.
    This ensures the loop looking for 'details_paragraph' completes without breaking,
    and the subsequent 'if details_paragraph:' block is skipped.
    """
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
    assert results[0]["format"] == "Unknown"


def test_fetch_and_parse_page_missing_title():
    """
    Test a post that is missing the title element.
    This should trigger the 'continue' statement early in the loop.
    """
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


def test_fetch_page_post_exception(caplog):
    session = MagicMock()
    session.get.return_value.text = "<html></html>"
    session.get.return_value.status_code = 200

    mock_post = MagicMock()
    mock_post.select_one.side_effect = Exception("Post Error")

    # Correct patching of BeautifulSoup in app.scraper.core where it is imported
    with patch("app.scraper.core.BeautifulSoup") as mock_bs:
        mock_bs.return_value.select.return_value = [mock_post]
        with caplog.at_level(logging.ERROR):
            results = fetch_and_parse_page(session, "host", "q", 1, "ua")
            assert results == []
            assert "Could not process post" in caplog.text


def test_fetch_page_urljoin_exception(real_world_html):
    session = MagicMock()
    session.get.return_value.text = real_world_html
    session.get.return_value.status_code = 200

    # Correct patching of urljoin in app.scraper.core where it is imported
    with patch("app.scraper.core.urljoin", side_effect=Exception("Join Error")):
        results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert results == []


def test_fetch_and_parse_page_missing_cover_image():
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Cover</a></h2></div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    # Expect None so UI handles versioning
    assert results[0]["cover"] is None


def test_fetch_and_parse_page_missing_post_info():
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Info</a></h2></div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    assert results[0]["language"] == "Unknown"


def test_fetch_and_parse_page_remote_default_cover_optimization():
    """
    Test that if a remote cover image is detected as the 'default' placeholder,
    it is replaced with None to allow the UI to serve the local versioned default.
    """
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
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    results = fetch_and_parse_page(session, "host", "q", 1, "ua")
    # Assert it was converted to None (logic updated from previous local path assumption)
    assert results[0]["cover"] is None


# --- Get Book Details Tests ---


def test_get_book_details_sanitization(mock_sleep):
    """
    Test strict HTML sanitization in get_book_details.
    Covers core.py lines around sanitization logic (looping through tags, unwrapping, etc).
    """
    # Create HTML with mix of allowed and disallowed tags
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

        description = details["description"]

        # Verify allowed tags are kept but stripped of attributes
        assert "<p>Allowed P tag.</p>" in description
        assert "style" not in description  # Attribute stripped

        # Verify allowed formatting tags are kept
        assert "<b>Bold Text</b>" in description

        # Verify disallowed tags are unwrapped (content remains, tag gone)
        assert "Malicious Link" in description
        assert "<a href" not in description

        # Verify scripts are sanitized (BeautifulSoup unwrap removes the tag)
        assert "<script>" not in description


def test_get_book_details_success(details_html, mock_sleep):
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
        # Verify line 272 (description link cleaning) worked:
        assert "Spam Link" in details["description"]
        assert "<a href" not in details["description"]

        # EXPLICITLY CHECK METADATA to ensure regex lines (206, 254) are hit
        assert details["language"] == "English"
        assert details["category"] == "Fantasy"
        assert details["post_date"] == "10 Jan 2024"


def test_get_book_details_default_cover_skip(mock_sleep):
    """
    Test that if details page has the default cover, it is skipped (None).
    This covers the condition `if "default_cover.jpg" not in extracted_cover:` evaluating to False.
    """
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


def test_get_book_details_failure(mock_sleep):
    with patch("requests.Session.get", side_effect=requests.exceptions.RequestException("Net Down")):
        with pytest.raises(requests.exceptions.RequestException):
            get_book_details("https://audiobookbay.lu/fail-book")


def test_get_book_details_ssrf_protection():
    """Test that get_book_details rejects non-ABB domains."""
    with pytest.raises(ValueError) as exc:
        get_book_details("https://google.com/admin")
    assert "Invalid domain" in str(exc.value)


def test_get_book_details_empty(mock_sleep):
    with pytest.raises(ValueError) as exc:
        get_book_details("")
    assert "No URL provided" in str(exc.value)


def test_get_book_details_url_parse_error(mock_sleep):
    with patch("app.scraper.core.urlparse", side_effect=Exception("Boom")):
        with pytest.raises(ValueError) as exc:
            get_book_details("http://anything")
    assert "Invalid URL format" in str(exc.value)


def test_get_book_details_missing_metadata(mock_sleep):
    html = """<div class="post"><div class="postTitle"><h1>Empty Book</h1></div></div>"""
    with patch("requests.Session.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_get.return_value = mock_response
        details = get_book_details("https://audiobookbay.lu/empty")
        assert details["language"] == "Unknown"
        assert details["format"] == "Unknown"


def test_get_book_details_unknown_bitrate_normalization(mock_sleep):
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


def test_get_book_details_partial_bitrate(mock_sleep):
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


def test_get_book_details_partial_format(mock_sleep):
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


def test_get_book_details_content_without_metadata_labels(mock_sleep):
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


def test_get_book_details_consistency_checks(mock_sleep):
    """
    Test that '?' values in detailed metadata are converted to 'Unknown'.
    Covers app/scraper/core.py lines 308-318.
    UPDATED: Added 'Bitrate: ?' to cover line 223.
    """
    html = """
    <div class="post">
        <div class="postTitle"><h1>Mystery Details</h1></div>
        <div class="postInfo">Category: ? Language: ?</div>
        <div class="postContent">
            <p>Posted: ?</p>
            <p>Format: ?</p>
            <p>Bitrate: ?</p>
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
        assert details["bitrate"] == "Unknown"
        assert details["author"] == "Unknown"
        assert details["narrator"] == "Unknown"
        assert details["file_size"] == "Unknown"
