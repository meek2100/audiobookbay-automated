"""Tests for fetch_page_results."""

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
import requests_mock

from audiobook_automated.scraper import fetch_page_results, get_search_url


def fetch_and_parse_page(hostname: str, query: str, page: int, user_agent: str, timeout: int) -> list[dict[str, Any]]:
    """Helper to mimic old fetch_and_parse_page using new primitives."""
    base_url = f"https://{hostname}"
    url = get_search_url(base_url, query, page)
    return fetch_page_results(url)


def test_fetch_and_parse_page_real_structure(real_world_html: str, mock_sleep: Any) -> None:
    """Test the end-to-end fetching and parsing logic using a real HTML snippet."""
    hostname = "audiobookbay.lu"
    query = "test"
    page = 1

    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=real_world_html, status_code=200)

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page(hostname, query, page, "ua", 30)

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

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["bitrate"] == "Unknown"


def test_fetch_and_parse_page_malformed() -> None:
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text="<html><body></body></html>", status_code=200)

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results == []


def test_fetch_and_parse_page_zero_results(mock_sleep: Any) -> None:
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

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page("host", "nonexistent", 1, "ua", 30)
    assert results == []


def test_fetch_and_parse_page_mixed_validity() -> None:
    mixed_html = """
    <div class="post"><div>Broken Info</div></div>
    <div class="post">
        <div class="postTitle"><h2><a href="/valid">Valid Book</a></h2></div>
        <div class="postContent"><p>Valid Content</p></div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=mixed_html, status_code=200)

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
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

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["format"] == "Unknown"


def test_fetch_and_parse_page_language_fallback() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postInfo">Languages: English</div>
        <div class="postContent"><p>Content</p></div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["language"] == "Unknown"


def test_fetch_and_parse_page_missing_regex_matches() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">T</a></h2></div>
        <div class="postInfo">No recognizable labels here</div>
        <div class="postContent"><p>Content</p></div>
    </div>
    """
    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)
    adapter.register_uri("GET", "https://host/page/1/?s=q", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["language"] == "Unknown"
    assert results[0]["category"] == ["Unknown"]


def test_fetch_and_parse_page_no_posted_date() -> None:
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

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
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

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page(hostname, query, 1, "UA", 30)
    assert results == []


def test_fetch_page_post_exception(caplog: Any) -> None:
    mock_session = MagicMock()
    mock_session.get.return_value.text = "<html></html>"
    mock_session.get.return_value.status_code = 200

    mock_post = MagicMock()
    mock_post.select_one.side_effect = Exception("Post Error")

    with patch("audiobook_automated.scraper.parser.BeautifulSoup") as mock_bs:
        mock_bs.return_value.select.return_value = [mock_post]
        with caplog.at_level(logging.ERROR):
            with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
                with patch("audiobook_automated.scraper.core.network.get_semaphore"):
                    results = fetch_and_parse_page("host", "q", 1, "ua", 30)
            assert results == []


def test_fetch_page_urljoin_exception(real_world_html: str) -> None:
    mock_session = MagicMock()
    mock_session.get.return_value.text = real_world_html
    mock_session.get.return_value.status_code = 200

    with patch("audiobook_automated.scraper.parser.urljoin", side_effect=Exception("Join Error")):
        with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
            with patch("audiobook_automated.scraper.core.network.get_semaphore"):
                results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results == []


def test_fetch_and_parse_page_missing_cover_image() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Cover</a></h2></div>
        <div class="postContent"><p>Content</p></div>
    </div>
    """
    mock_session = requests.Session()
    with patch.object(mock_session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
            with patch("audiobook_automated.scraper.core.network.get_semaphore"):
                results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["cover"] is None


def test_fetch_and_parse_page_missing_post_info() -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">No Info</a></h2></div>
        <div class="postContent"><p>Content</p></div>
    </div>
    """
    mock_session = requests.Session()
    with patch.object(mock_session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
            with patch("audiobook_automated.scraper.core.network.get_semaphore"):
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
        with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
            with patch("audiobook_automated.scraper.core.network.get_semaphore"):
                results = fetch_and_parse_page("host", "q", 1, "ua", 30)
    assert results[0]["cover"] is None


def test_fetch_and_parse_page_missing_content_div(caplog: Any) -> None:
    html = """
    <div class="post">
        <div class="postTitle"><h2><a href="/link">Empty</a></h2></div>
        <!-- Missing postContent -->
    </div>
    """
    mock_session = requests.Session()
    with patch.object(mock_session, "get") as mock_get:
        mock_get.return_value.text = html
        mock_get.return_value.status_code = 200
        with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
            with patch("audiobook_automated.scraper.core.network.get_semaphore"):
                with caplog.at_level(logging.WARNING):
                    results = fetch_and_parse_page("host", "q", 1, "ua", 30)

    assert results == []


def test_fetch_page_special_characters(real_world_html: str, mock_sleep: Any) -> None:
    hostname = "audiobookbay.lu"
    query = "Batman & Robin [Special Edition]"
    page = 1
    user_agent = "TestAgent/1.0"

    mock_session = requests.Session()
    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch.object(mock_session, "get") as mock_get:
            mock_get.return_value.text = real_world_html
            mock_get.return_value.status_code = 200

            with patch("audiobook_automated.scraper.core.network.get_semaphore"):
                fetch_and_parse_page(hostname, query, page, user_agent, 30)

            # Verify the query was passed in the params dict
            mock_get.assert_called()
            args = mock_get.call_args
            assert query in args[0][0]


def test_fetch_page_timeout(mock_sleep: Any) -> None:
    hostname = "audiobookbay.lu"
    query = "timeout"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)
    adapter.register_uri("GET", f"https://{hostname}/page/1/?s={query}", exc=requests.exceptions.Timeout)

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page(hostname, query, page, user_agent, 30)
            assert results == []


def test_fetch_and_parse_page_consistency_checks(mock_sleep: Any) -> None:
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
    adapter.register_uri("GET", f"https://{hostname}/page/1/?s={query}", text=html, status_code=200)

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
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
    hostname = "audiobookbay.lu"
    query = "test"
    page = 2
    user_agent = "TestAgent/1.0"

    mock_session = requests.Session()
    adapter = requests_mock.Adapter()
    mock_session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=real_world_html, status_code=200)

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_and_parse_page(hostname, query, page, user_agent, 30)

    assert len(results) == 1
