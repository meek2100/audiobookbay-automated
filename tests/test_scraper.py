import requests_mock

from app.scraper import fetch_and_parse_page

# Real HTML structure taken from GOT_ABB.html provided by user
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

    with requests_mock.Mocker() as m:
        # Mock the external HTTP request
        m.get(f"https://{hostname}/page/1/?s={query}", text=REAL_WORLD_HTML, status_code=200)

        results = fetch_and_parse_page(hostname, query, 1)

        assert len(results) == 1
        book = results[0]

        # Verify robust extraction
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

    with requests_mock.Mocker() as m:
        m.get(f"https://{hostname}/page/1/?s={query}", text="<html><body></body></html>", status_code=200)

        results = fetch_and_parse_page(hostname, query, 1)
        assert results == []
