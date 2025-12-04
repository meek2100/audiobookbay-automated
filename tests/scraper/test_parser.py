import logging
from unittest.mock import MagicMock, patch

import requests
import requests_mock
from bs4 import BeautifulSoup

from app.scraper import fetch_and_parse_page, get_text_after_label

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
    assert result == "N/A"


def test_get_text_after_label_fallback():
    """Test that it returns 'N/A' if label exists but no value follows."""

    class FakeNavigableString(str):
        def find_next_sibling(self):
            return None

    mock_container = MagicMock()
    mock_label_node = FakeNavigableString("Format:")
    mock_container.find.return_value = mock_label_node

    result = get_text_after_label(mock_container, "Format:")
    assert result == "N/A"


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
    assert results[0]["format"] == "N/A"


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
    assert results[0]["language"] == "N/A"


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
    assert results[0]["language"] == "N/A"
    assert results[0]["category"] == "N/A"


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
    assert results[0]["post_date"] == "N/A"
    assert results[0]["format"] == "N/A"


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
    assert results[0]["cover"] == "/static/images/default_cover.jpg"


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
    assert results[0]["language"] == "N/A"
