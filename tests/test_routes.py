from unittest.mock import patch


def test_home_page_load(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Search AudiobookBay" in response.data


def test_status_page(client):
    with patch("app.app.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = [{"name": "Book 1", "progress": 50, "state": "Downloading", "size": "100 MB"}]
        response = client.get("/status")
        assert response.status_code == 200
        assert b"Book 1" in response.data


def test_send_success(client):
    """Test successful magnet link generation and sending."""
    with patch("app.app.extract_magnet_link") as mock_extract, patch("app.app.torrent_manager") as mock_tm:
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)

        response = client.post("/send", json={"link": "https://audiobookbay.lu/book-page", "title": "Test Book"})

        assert response.status_code == 200
        mock_tm.add_magnet.assert_called_once()
        assert b"Download added successfully" in response.data


def test_send_missing_data(client):
    """Test API rejects requests without link or title."""
    response = client.post("/send", json={"link": "http://example.com"})
    assert response.status_code == 400
    assert b"Invalid request" in response.data


def test_send_extraction_failure(client):
    """Test handling of magnet extraction errors."""
    with patch("app.app.extract_magnet_link") as mock_extract:
        mock_extract.return_value = (None, "Page Not Found")

        response = client.post("/send", json={"link": "https://audiobookbay.lu/bad-page", "title": "Bad Book"})

        assert response.status_code == 500
        assert b"Download failed: Page Not Found" in response.data


def test_send_torrent_client_failure(client):
    """Test handling of torrent client connection errors."""
    with patch("app.app.extract_magnet_link") as mock_extract, patch("app.app.torrent_manager") as mock_tm:
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
        # Simulate a crash in the torrent manager
        mock_tm.add_magnet.side_effect = Exception("Connection Refused")

        response = client.post("/send", json={"link": "https://audiobookbay.lu/book-page", "title": "Test Book"})

        assert response.status_code == 500
        assert b"Connection Refused" in response.data


def test_search_exception_handling(client):
    """Test that backend errors during search are shown to user gracefully."""
    with patch("app.app.search_audiobookbay") as mock_search:
        mock_search.side_effect = Exception("Connection timed out")

        # Simulate a search POST request
        response = client.post("/", data={"query": "my book"})

        assert response.status_code == 200
        # Check if error message is rendered in the template
        assert b"Unable to connect to AudiobookBay" in response.data
        assert b"Connection timed out" in response.data


def test_nav_link_injection(client, monkeypatch):
    """Test that environment variables correctly inject the nav link."""
    monkeypatch.setenv("NAV_LINK_NAME", "My Player")
    monkeypatch.setenv("NAV_LINK_URL", "http://player.local")

    # We need to reload the app/client or just check the context processor behavior
    # simpler to check response content since context processors run per request
    response = client.get("/")
    assert b"My Player" in response.data
    assert b"http://player.local" in response.data
