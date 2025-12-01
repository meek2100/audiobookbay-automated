from unittest.mock import MagicMock, patch

import requests


def test_home_page_load(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Search AudiobookBay" in response.data


def test_health_check_route(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_status_page(client):
    with patch("app.app.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = [{"name": "Book 1", "progress": 50, "state": "Downloading", "size": "100 MB"}]
        response = client.get("/status")
        assert response.status_code == 200
        assert b"Book 1" in response.data


def test_status_route_error(client):
    """Test /status route when client raises generic exception."""
    with patch("app.app.torrent_manager") as mock_tm:
        mock_tm.get_status.side_effect = Exception("Database Locked")

        response = client.get("/status")
        assert response.status_code == 200
        assert b"Error connecting to client" in response.data
        assert b"Database Locked" in response.data


def test_send_success(client):
    with patch("app.app.extract_magnet_link") as mock_extract, patch("app.app.torrent_manager") as mock_tm:
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
        response = client.post("/send", json={"link": "https://audiobookbay.lu/book-page", "title": "Test Book"})
        assert response.status_code == 200
        mock_tm.add_magnet.assert_called_once()


def test_send_missing_data(client):
    response = client.post("/send", json={"link": "http://example.com"})
    assert response.status_code == 400
    assert b"Invalid request" in response.data


def test_send_extraction_failure(client):
    with patch("app.app.extract_magnet_link") as mock_extract:
        mock_extract.return_value = (None, "Page Not Found")
        response = client.post("/send", json={"link": "https://audiobookbay.lu/bad-page", "title": "Bad Book"})
        assert response.status_code == 500
        assert b"Download failed: Page Not Found" in response.data


def test_send_torrent_client_failure(client):
    with patch("app.app.extract_magnet_link") as mock_extract, patch("app.app.torrent_manager") as mock_tm:
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
        mock_tm.add_magnet.side_effect = Exception("Connection Refused")
        response = client.post("/send", json={"link": "https://audiobookbay.lu/book-page", "title": "Test Book"})
        assert response.status_code == 500
        assert b"Connection Refused" in response.data


def test_send_route_no_save_path_base(client, monkeypatch, app_module):
    """Test the 'else' branch where SAVE_PATH_BASE is None (logic coverage)."""
    # Use app_module fixture
    monkeypatch.setattr(app_module, "SAVE_PATH_BASE", None)

    with patch("app.app.extract_magnet_link", return_value=("magnet:...", None)):
        with patch("app.app.torrent_manager") as mock_tm:
            response = client.post("/send", json={"link": "l", "title": "t"})
            assert response.status_code == 200
            mock_tm.add_magnet.assert_called_with("magnet:...", "t")


def test_search_exception_handling(client):
    with patch("app.app.search_audiobookbay") as mock_search:
        mock_search.side_effect = Exception("Connection timed out")
        response = client.post("/", data={"query": "my book"})
        assert response.status_code == 200
        assert b"Search Failed: Connection timed out" in response.data


def test_nav_link_injection(client, monkeypatch, app_module):
    """Test that injected variables correctly appear in the template."""
    monkeypatch.setattr(app_module, "NAV_LINK_NAME", "My Player")
    monkeypatch.setattr(app_module, "NAV_LINK_URL", "http://player.local")
    response = client.get("/")
    assert b"My Player" in response.data
    assert b"http://player.local" in response.data


def test_delete_torrent(client):
    with patch("app.app.torrent_manager") as mock_tm:
        mock_tm.remove_torrent.return_value = None
        response = client.post("/delete", json={"id": "hash123"})
        assert response.status_code == 200
        mock_tm.remove_torrent.assert_called_with("hash123")


def test_delete_torrent_missing_id(client):
    response = client.post("/delete", json={})
    assert response.status_code == 400
    assert b"Torrent ID is required" in response.data


def test_delete_torrent_failure(client):
    with patch("app.app.torrent_manager") as mock_tm:
        mock_tm.remove_torrent.side_effect = Exception("Removal failed")
        response = client.post("/delete", json={"id": "hash123"})
        assert response.status_code == 500
        assert b"Removal failed" in response.data


def test_reload_library_success(client, monkeypatch, app_module):
    monkeypatch.setattr(app_module, "LIBRARY_RELOAD_ENABLED", True)
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


def test_reload_library_not_configured(client, monkeypatch, app_module):
    monkeypatch.setattr(app_module, "LIBRARY_RELOAD_ENABLED", False)
    response = client.post("/reload_library")
    assert response.status_code == 400
    assert b"not configured" in response.data


def test_reload_library_detailed_error(client, monkeypatch, app_module):
    """Test /reload_library when requests raises an error WITH a response object."""
    monkeypatch.setattr(app_module, "LIBRARY_RELOAD_ENABLED", True)

    with (
        patch("app.app.AUDIOBOOKSHELF_URL", "http://abs"),
        patch("app.app.ABS_KEY", "k"),
        patch("app.app.ABS_LIB", "l"),
    ):
        with patch("app.app.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_resp.reason = "Service Unavailable"
            mock_resp.text = "Busy"

            exc = requests.exceptions.RequestException("Request Failed")
            exc.response = mock_resp
            mock_post.side_effect = exc

            response = client.post("/reload_library")
            assert response.status_code == 500
            assert "503 Service Unavailable" in response.json["message"]


# --- Rate Limiter Tests ---


def test_rate_limit_enforced(client):
    """Test that the /send endpoint enforces the rate limit."""
    # Force enable limiter for this test context
    client.application.config["RATELIMIT_ENABLED"] = True

    with patch("app.app.extract_magnet_link") as mock_extract, patch("app.app.torrent_manager") as mock_tm:
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
        mock_tm.add_magnet.return_value = None

        # Send 60 allowed requests
        for _ in range(60):
            response = client.post("/send", json={"link": "http://example.com/book", "title": "Test Book"})
            assert response.status_code == 200

        # The 61st request should be blocked
        response = client.post("/send", json={"link": "http://example.com/book", "title": "Test Book"})
        assert response.status_code == 429


def test_rate_limit_headers(client):
    """Test that rate limit headers are returned."""
    client.application.config["RATELIMIT_ENABLED"] = True

    with patch("app.app.extract_magnet_link") as mock_extract, patch("app.app.torrent_manager") as mock_tm:
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
        mock_tm.add_magnet.return_value = None

        response = client.post("/send", json={"link": "http://example.com/book", "title": "Header Test"})
        assert response.status_code == 200

        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
