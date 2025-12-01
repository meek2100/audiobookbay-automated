from unittest.mock import patch


def test_home_page_load(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Search AudiobookBay" in response.data


def test_health_check_route(client):
    """Test the dedicated health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


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
        assert b"Unable to connect to AudiobookBay" in response.data or b"Connection timed out" in response.data


def test_nav_link_injection(client, monkeypatch):
    """Test that environment variables correctly inject the nav link."""
    monkeypatch.setenv("NAV_LINK_NAME", "My Player")
    monkeypatch.setenv("NAV_LINK_URL", "http://player.local")

    # We need to reload the app/client or just check the context processor behavior
    # simpler to check response content since context processors run per request
    response = client.get("/")
    assert b"My Player" in response.data
    assert b"http://player.local" in response.data


def test_delete_torrent(client):
    """Test the delete endpoint calls the manager and returns success."""
    with patch("app.app.torrent_manager") as mock_tm:
        mock_tm.remove_torrent.return_value = None
        response = client.post("/delete", json={"id": "hash123"})
        assert response.status_code == 200
        mock_tm.remove_torrent.assert_called_with("hash123")


def test_delete_torrent_missing_id(client):
    """Test that delete endpoint rejects requests without an ID."""
    response = client.post("/delete", json={})
    assert response.status_code == 400
    assert b"Torrent ID is required" in response.data


def test_delete_torrent_failure(client):
    """Test handling of removal errors."""
    with patch("app.app.torrent_manager") as mock_tm:
        mock_tm.remove_torrent.side_effect = Exception("Removal failed")
        response = client.post("/delete", json={"id": "hash123"})
        assert response.status_code == 500
        assert b"Removal failed" in response.data


def test_reload_library_success(client):
    """Test ABS reload triggers correctly."""
    # We must patch the globals in app.app because they are loaded at import time
    with (
        patch("app.app.AUDIOBOOKSHELF_URL", "http://abs"),
        patch("app.app.ABS_KEY", "token"),
        patch("app.app.ABS_LIB", "lib-id"),
        patch("app.app.requests.post") as mock_post,
    ):
        mock_post.return_value.status_code = 200

        response = client.post("/reload_library")

        assert response.status_code == 200
        assert b"scan initiated" in response.data
        mock_post.assert_called_once()


def test_reload_library_not_configured(client):
    """Test ABS reload fails gracefully when not configured."""
    # Ensure one is missing
    with patch("app.app.AUDIOBOOKSHELF_URL", None):
        response = client.post("/reload_library")
        assert response.status_code == 400
        assert b"not configured" in response.data
