from unittest.mock import patch

import pytest
import requests
import requests_mock

from app.scraper import extract_magnet_link, fetch_and_parse_page, mirror_cache, search_audiobookbay

REAL_WORLD_HTML = """
<div class="post">
    <div class="postTitle">
        <h2><a href="/abss/moster-walter-dean-myers/" rel="bookmark">Moster - Walter Dean Myers</a></h2>
    </div>
    <div class="postInfo">
        Category: Crime Full Cast General Fiction Teen & Young Adult <br>
        Language: English<span style="margin-left:100px;">Keywords: Black TRIAL </span><br>
    </div>
    <div class="postContent">
        <div class="center">
            <p class="center">Shared by:<a href="#">FissionMailed</a></p>
            <p class="center">
                <a href="/abss/moster-walter-dean-myers/">
                    <img src="/images/cover.jpg" alt="Walter Dean Myers Moster" width="250">
                </a>
            </p>
        </div>
        <p style="center;"></p>
        <p style="text-align:center;">
            Posted: 30 Nov 2025<br>
            Format: <span style="color:#a00;">MP3</span> / Bitrate: <span style="color:#a00;">96 Kbps</span><br>
            File Size: <span style="color:#00f;">106.91</span> MBs
        </p>
    </div>
</div>
"""


def test_fetch_and_parse_page_real_structure():
    hostname = "audiobookbay.lu"
    query = "test"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", text=REAL_WORLD_HTML, status_code=200)

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)

    assert len(results) == 1
    book = results[0]
    assert book["title"] == "Moster - Walter Dean Myers"
    assert book["language"] == "English"
    assert book["format"] == "MP3"
    assert book["bitrate"] == "96 Kbps"
    assert book["file_size"] == "106.91 MBs"
    assert book["post_date"] == "30 Nov 2025"

    # Verify URL joining works (relative -> absolute)
    assert book["link"] == "https://audiobookbay.lu/abss/moster-walter-dean-myers/"
    assert book["cover"] == "https://audiobookbay.lu/images/cover.jpg"


def test_fetch_and_parse_page_malformed():
    """Test resilience against empty/broken HTML"""
    hostname = "audiobookbay.lu"
    query = "bad"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri(
        "GET", f"https://{hostname}/page/{page}/?s={query}", text="<html><body></body></html>", status_code=200
    )

    results = fetch_and_parse_page(session, hostname, query, page, user_agent)
    assert results == []


def test_fetch_page_timeout():
    """Test that connection timeouts are handled gracefully."""
    hostname = "audiobookbay.lu"
    query = "timeout"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    # Simulate a timeout
    adapter.register_uri("GET", f"https://{hostname}/page/{page}/?s={query}", exc=requests.exceptions.Timeout)

    # Should return empty list, not crash
    results = fetch_and_parse_page(session, hostname, query, page, user_agent)
    assert results == []


def test_extract_magnet_no_hash():
    """Test handling of pages where info hash cannot be found."""
    details_url = "https://audiobookbay.lu/audiobook-details"

    # HTML with missing info hash table and missing regex pattern
    broken_html = """
    <html>
        <body>
            <table>
                <tr><td>Some other data</td></tr>
            </table>
        </body>
    </html>
    """

    with requests_mock.Mocker() as m:
        m.get(details_url, text=broken_html)
        magnet, error = extract_magnet_link(details_url)
        assert magnet is None
        assert "Info Hash could not be found" in error


def test_search_no_mirrors_raises_error():
    """Test that search raises ConnectionError when no mirrors are found."""
    # Ensure cache is empty
    mirror_cache.clear()

    with patch("app.scraper.find_best_mirror") as mock_find:
        mock_find.return_value = None

        with pytest.raises(ConnectionError) as exc:
            search_audiobookbay("test")

        assert "No reachable AudiobookBay mirrors" in str(exc.value)
