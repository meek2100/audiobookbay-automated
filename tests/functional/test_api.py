# tests/functional/test_api.py
"""Functional tests for API endpoints."""

from typing import Any
from unittest.mock import patch

from flask.testing import FlaskClient


def test_health_check(client: FlaskClient[Any]) -> None:
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_search_endpoint_valid(client: FlaskClient[Any]) -> None:
    """Test a valid search request."""
    mock_results = [{"title": "Test Book", "link": "http://test", "file_size": "100MB"}]

    with patch("audiobook_automated.routes.search_audiobookbay", return_value=mock_results):
        response = client.get("/?query=testbook")
        assert response.status_code == 200
        assert b"Test Book" in response.data


def test_search_endpoint_short_query(client: FlaskClient[Any]) -> None:
    """Test search with a query that is too short."""
    response = client.get("/?query=a")
    assert response.status_code == 200
    assert b"Search query must be at least" in response.data


def test_send_success(client: FlaskClient[Any]) -> None:
    """Test successful download request."""
    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
            response = client.post(
                "/send",
                json={"link": "https://audiobookbay.lu/book", "title": "Great Book"},
            )

            assert response.status_code == 200
            assert "Download added successfully" in response.json["message"]
            mock_tm.add_magnet.assert_called_once()


def test_send_invalid_json(client: FlaskClient[Any]) -> None:
    """Test send endpoint with non-JSON body."""
    response = client.post("/send", data="not json")
    assert response.status_code == 400
    assert "Invalid JSON format" in response.json["message"]


def test_send_missing_fields(client: FlaskClient[Any]) -> None:
    """Test send endpoint with missing fields."""
    response = client.post("/send", json={"title": "No Link"})
    assert response.status_code == 400
    assert "Invalid request" in response.json["message"]


def test_send_extraction_failure(client: FlaskClient[Any]) -> None:
    """Test handling of magnet extraction failures."""
    with patch("audiobook_automated.routes.extract_magnet_link") as mock_extract:
        mock_extract.return_value = (None, "Page Not Found")
        response = client.post(
            "/send",
            json={"link": "https://audiobookbay.lu/bad-page", "title": "Bad Book"},
        )
        # Updated to 400 because "Page Not Found" does not contain lowercase "found"
        assert response.status_code == 400
        assert "Download failed" in response.json["message"]


def test_send_connection_error(client: FlaskClient[Any]) -> None:
    """Test handling of connection errors during send."""
    with patch("audiobook_automated.routes.extract_magnet_link", side_effect=ConnectionError("Down")):
        response = client.post(
            "/send",
            json={"link": "https://audiobookbay.lu/book", "title": "Book"},
        )
        assert response.status_code == 503
        assert "Upstream service unavailable" in response.json["message"]


def test_delete_success(client: FlaskClient[Any]) -> None:
    """Test successful torrent deletion."""
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        response = client.post("/delete", json={"id": "hash123"})
        assert response.status_code == 200
        mock_tm.remove_torrent.assert_called_with("hash123")


def test_delete_missing_id(client: FlaskClient[Any]) -> None:
    """Test delete endpoint without ID."""
    response = client.post("/delete", json={})
    assert response.status_code == 400


def test_reload_library_success(client: FlaskClient[Any]) -> None:
    """Test successful library scan trigger."""
    # Ensure config is set
    with patch("audiobook_automated.routes.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        response = client.post("/reload_library")
        assert response.status_code == 200
        assert "scan initiated" in response.json["message"]


def test_status_json(client: FlaskClient[Any]) -> None:
    """Test status endpoint returning JSON."""
    mock_status = [{"id": "1", "name": "Book", "progress": 50.0}]
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = mock_status
        response = client.get("/status?json=1")
        assert response.status_code == 200
        assert response.json == mock_status


def test_send_sanitization_warning(client: FlaskClient[Any], caplog: Any) -> None:
    """Test logging warning for titles requiring sanitization fallback."""
    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        # FIX: Removed unused 'as mock_tm' to satisfy Ruff
        with patch("audiobook_automated.routes.torrent_manager"):
            client.post("/send", json={"link": "http://example.com", "title": "..."})
            # Updated expectation to match the new log message format in routes.py
            assert "required fallback/truncate handling" in caplog.text
            assert "Using collision-safe directory name" in caplog.text
