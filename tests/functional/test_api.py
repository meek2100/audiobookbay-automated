from unittest.mock import MagicMock, patch

import requests


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


def test_send_malformed_json(client):
    response = client.post("/send", data="not json", content_type="application/json")
    assert response.status_code == 400


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
    monkeypatch.setattr(app_module, "SAVE_PATH_BASE", None)
    with patch("app.app.extract_magnet_link", return_value=("magnet:...", None)):
        with patch("app.app.torrent_manager") as mock_tm:
            response = client.post("/send", json={"link": "l", "title": "t"})
            assert response.status_code == 200
            mock_tm.add_magnet.assert_called_with("magnet:...", "t")


def test_send_sanitization_warning(client, caplog):
    """Test that titles sanitizing to empty fallback to Unknown_Title."""
    with patch("app.app.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        with patch("app.app.torrent_manager") as mock_tm:
            client.post("/send", json={"link": "http://example.com", "title": "..."})
            assert "Title '...' was sanitized to fallback 'Unknown_Title'" in caplog.text
            args, _ = mock_tm.add_magnet.call_args
            assert "Unknown_Title" in args[1]


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
        patch("app.app.ABS_URL", "http://abs"),
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
    monkeypatch.setattr(app_module, "LIBRARY_RELOAD_ENABLED", True)
    with (
        patch("app.app.ABS_URL", "http://abs"),
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


def test_rate_limit_enforced(client):
    """Test that the /send endpoint enforces the rate limit."""
    client.application.config["RATELIMIT_ENABLED"] = True
    with patch("app.app.extract_magnet_link", return_value=("magnet:123", None)), patch("app.app.torrent_manager"):
        for _ in range(60):
            response = client.post("/send", json={"link": "l", "title": "t"})
            assert response.status_code == 200

        response = client.post("/send", json={"link": "l", "title": "t"})
        assert response.status_code == 429


def test_rate_limit_headers(client):
    client.application.config["RATELIMIT_ENABLED"] = True
    with patch("app.app.extract_magnet_link", return_value=("magnet:123", None)), patch("app.app.torrent_manager"):
        response = client.post("/send", json={"link": "l", "title": "t"})
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
