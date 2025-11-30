import requests_mock
from app.scraper import fetch_and_parse_page

# Hermeneutic Circle: Testing the "Parts" (HTML parsing) ensures the "Whole" (User Search) works.

MOCK_HTML = """
<html>
<body>
    <div class="post">
        <div class="postTitle">
            <h2><a href="/audiobook-details">Test Audiobook Title</a></h2>
        </div>
        <img src="/cover.jpg" />
        <div class="postInfo">
            Language: English
            Keywords: Fantasy
        </div>
        <div class="postContent">
            <p style="text-align:center">
                Posted: 10 Jan 2024<br/>
                Format: <span>MP3</span><br/>
                Bitrate: <span>64 kbps</span><br/>
                File Size: <span>100</span> MB
            </p>
        </div>
    </div>
</body>
</html>
"""

def test_fetch_and_parse_page_success():
    hostname = "audiobookbay.lu"
    query = "test"

    with requests_mock.Mocker() as m:
        # Mock the external HTTP request
        m.get(f"https://{hostname}/page/1/?s={query}", text=MOCK_HTML, status_code=200)

        results = fetch_and_parse_page(hostname, query, 1)

        assert len(results) == 1
        book = results[0]
        assert book['title'] == "Test Audiobook Title"
        assert book['language'] == "English"
        assert book['format'] == "MP3"
        assert book['bitrate'] == "64 kbps"
        assert book['file_size'] == "100 MB"
        assert "audiobookbay.lu" in book['link']

def test_fetch_and_parse_page_malformed():
    """Test resilience against empty/broken HTML"""
    hostname = "audiobookbay.lu"
    query = "bad"

    with requests_mock.Mocker() as m:
        m.get(f"https://{hostname}/page/1/?s={query}", text="<html><body></body></html>", status_code=200)

        results = fetch_and_parse_page(hostname, query, 1)
        assert results == []