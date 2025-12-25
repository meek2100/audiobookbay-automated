# File: tests/scraper/test_fetcher.py
"""Tests for fetch_and_parse_page."""

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
import requests_mock

from audiobook_automated.scraper import fetch_and_parse_page


def test_fetch_and_parse_page_real_structure(real_world_html: str, mock_sleep: Any) -> None:
    """Test the end-to-end fetching and parsing logic using a real HTML snippet."""
    hostname = "audiobookbay.lu"
    query = "test"
    page = 1
    user_agent = "TestAgent/1.0"

    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)

    # Page 1 now uses root URL
    adapter.register_uri("GET", f"https://{hostname}/?s={query}", text=real_world_html, status_code=200)

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
    """Test that '?' bitrates are correctly parsed as 'Unknown'."""
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
    adapter.register_uri("GET", "https://host/?s=q", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["bitrate"] == "Unknown"


def test_fetch_and_parse_page_malformed() -> None:
    """Test that malformed HTML (no posts) returns an empty list."""
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/?s=q", text="<html><body></body></html>", status_code=200)

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
    adapter.register_uri("GET", "https://host/?s=nonexistent", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "nonexistent", 1, "ua", 30)
    assert results == []


def test_fetch_and_parse_page_mixed_validity() -> None:
    """Test that the parser skips broken posts while retaining valid ones."""
    mixed_html = """
    <div class="post"><div>Broken Info</div></div>
    <div class="post">
        <div class="postTitle"><h2><a href="/valid">Valid Book</a></h2></div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/?s=q", text=mixed_html, status_code=200)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert len(results) == 1
    assert results[0]["title"] == "Valid Book"


def test_parsing_structure_change() -> None:
    """Test resilience against HTML structure changes (missing recognized tags)."""
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postContent"><p>Random text.</p></div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/?s=q", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["format"] == "Unknown"


def test_fetch_and_parse_page_language_fallback() -> None:
    """Test fallback when language regex fails to match."""
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postInfo">Languages: English</div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/?s=q", text=html, status_code=200)

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
    adapter.register_uri("GET", "https://host/?s=q", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["language"] == "Unknown"
    assert results[0]["category"] == ["Unknown"]


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
    adapter.register_uri("GET", f"https://{hostname}/?s={query}", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page(hostname, query, 1, "UA", 30)

    assert len(results) == 1
    assert results[0]["post_date"] == "Unknown"
    assert results[0]["format"] == "MP3"


def test_fetch_and_parse_page_missing_title() -> None:
    """Test that posts missing a title header are skipped."""
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
    adapter.register_uri("GET", f"https://{hostname}/?s={query}", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page(hostname, query, 1, "UA", 30)
    assert results == []


def test_fetch_page_post_exception(caplog: Any) -> None:
    """Test that exceptions raised during individual post parsing are logged and skipped."""
    mock_session = MagicMock()
    mock_session.get.return_value.text = "<html></html>"
    mock_session.get.return_value.status_code = 200

    mock_post = MagicMock()
    mock_post.select_one.side_effect = Exception("Post Error")

    with patch("audiobook_automated.scraper.core.BeautifulSoup") as mock_bs:
        mock_bs.return_value.select.return_value = [mock_post]
        with caplog.at_level(logging.ERROR):
            with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
                results = fetch_and_parse_page("host", "q", 1, "ua", 30)
            assert results == []
            assert "Could not process post" in caplog.text


def test_fetch_page_urljoin_exception(real_world_html: str) -> None:
    """Test that exceptions during URL joining return an empty list."""
    mock_session = MagicMock()
    mock_session.get.return_value.text = real_world_html
    mock_session.get.return_value.status_code = 200

    with patch("audiobook_automated.scraper.core.urljoin", side_effect=Exception("Join Error")):
        with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results == []


def test_fetch_and_parse_page_missing_cover_image() -> None:
    """Test that a missing cover image results in a None cover field."""
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Cover</a></h2></div>
    </div>
    """
    mock_session = requests.Session()
    with patch.object(mock_session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    # Expect None so UI handles versioning
    assert results[0]["cover"] is None


def test_fetch_and_parse_page_missing_post_info() -> None:
    """Test parsing logic when the 'postInfo' div is entirely missing."""
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Info</a></h2></div>
    </div>
    """
    mock_session = requests.Session()
    with patch.object(mock_session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["language"] == "Unknown"


def test_fetch_and_parse_page_remote_default_cover_optimization() -> None:
    """Test that the known 'default_cover.jpg' URL is converted to None."""
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
        with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    # Assert it was converted to None
    assert results[0]["cover"] is None


# --- From Integration ---


def test_fetch_page_special_characters(real_world_html: str, mock_sleep: Any) -> None:
    """Test that special characters in queries are passed correctly to the session."""
    hostname = "audiobookbay.lu"
    query = "Batman & Robin [Special Edition]"
    page = 1
    user_agent = "TestAgent/1.0"

    mock_session = requests.Session()
    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        with patch.object(mock_session, "get") as mock_get:
            mock_get.return_value.text = real_world_html
            mock_get.return_value.status_code = 200

            fetch_and_parse_page(hostname, query, page, user_agent, 30)

            # Verify the query was passed in the params dict
            mock_get.assert_called()
            call_args = mock_get.call_args
            assert call_args[1]["params"]["s"] == query


def test_fetch_page_timeout(mock_sleep: Any) -> None:
    """Test that timeouts propagate correctly."""
    hostname = "audiobookbay.lu"
    query = "timeout"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/?s={query}", exc=requests.exceptions.Timeout)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=session):
        with pytest.raises(requests.exceptions.Timeout):
            fetch_and_parse_page(hostname, query, page, user_agent, 30)


def test_fetch_and_parse_page_consistency_checks(mock_sleep: Any) -> None:
    """Test that '?' values in metadata are converted to 'Unknown'."""
    hostname = "audiobookbay.lu"
    query = "question_marks"
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/book">Mystery Book</a></h2></div>
        <div class="postInfo">Category: ? Language: ?</div>
        <div class="postContent">
            <p>Posted: ?<br>Format: ?<br>Bitrate: ?<br>File Size: ?</p>
        </div>
    </div>
    """
    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/?s={query}", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=session):
        results = fetch_and_parse_page(hostname, query, 1, "TestAgent/1.0", 30)

    assert len(results) == 1
    r = results[0]
    assert r["language"] == "Unknown"
    assert r["category"] == ["Unknown"]
    assert r["post_date"] == "Unknown"
    assert r["format"] == "Unknown"
    assert r["bitrate"] == "Unknown"
    assert r["file_size"] == "Unknown"


def test_fetch_and_parse_page_pagination(real_world_html: str, mock_sleep: Any) -> None:
    """Test fetching a page other than page 1 to verify pagination URL construction."""
    hostname = "audiobookbay.lu"
    query = "test"
    page = 2
    user_agent = "TestAgent/1.0"

    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)

    # Register URI for page 2
    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=real_world_html, status_code=200)

    with patch("audiobook_automated.scraper.core.get_thread_session", return_value=mock_session):
        results = fetch_and_parse_page(hostname, query, page, user_agent, 30)

    assert len(results) == 1
