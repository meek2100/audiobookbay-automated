# File: tests/functional/test_api.py
"""Functional tests for API endpoints."""

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

from audiobook_automated import create_app
from audiobook_automated.scraper.parser import BookDetails


def test_health_check(client: FlaskClient) -> None:
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_search_endpoint_valid(client: FlaskClient) -> None:
    """Test a valid search request."""
    mock_results = [{"title": "Test Book", "link": "http://test", "file_size": "100MB"}]

    with patch("audiobook_automated.routes.search_audiobookbay", return_value=mock_results):
        response = client.get("/?query=testbook")
        assert response.status_code == 200
        assert b"Test Book" in response.data


def test_search_endpoint_short_query(client: FlaskClient) -> None:
    """Test search with a query that is too short."""
    response = client.get("/?query=a")
    assert response.status_code == 200
    assert b"Search query must be at least" in response.data


def test_details_endpoint(client: FlaskClient) -> None:
    """Test the details endpoint rendering."""
    mock_details: BookDetails = {
        "title": "Detailed Book",
        "cover": "http://cover.jpg",
        "description": "<p>Desc</p>",
        "trackers": ["udp://tracker"],
        "file_size": "200MB",
        "info_hash": "12345",
        "link": "http://test/details",
        "language": "English",
        "category": ["Audiobook"],
        "post_date": "2025-01-01",
        "format": "MP3",
        "bitrate": "128kbps",
        "author": "Author",
        "narrator": "Narrator",
    }

    with patch("audiobook_automated.routes.get_book_details", return_value=mock_details):
        response = client.get("/details?link=http://test/details")
        assert response.status_code == 200
        assert b"Detailed Book" in response.data
        assert b"128kbps" in response.data


def test_details_missing_link(client: FlaskClient) -> None:
    """Test details endpoint redirects when link is missing."""
    response = client.get("/details")
    assert response.status_code == 302
    assert response.location == "/" or response.location == "http://localhost/"


def test_details_fetch_error(client: FlaskClient) -> None:
    """Test details endpoint error handling."""
    with patch("audiobook_automated.routes.get_book_details", side_effect=Exception("Fetch failed")):
        response = client.get("/details?link=http://test")
        assert response.status_code == 200
        assert b"Could not load details" in response.data


def test_send_success(client: FlaskClient) -> None:
    """Test successful download request."""
    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
            response = client.post(
                "/send",
                json={"link": "https://audiobookbay.lu/book", "title": "Great Book"},
            )

            assert response.status_code == 200
            assert response.json is not None
            assert "Download added successfully" in response.json["message"]
            mock_tm.add_magnet.assert_called_once()


def test_send_invalid_json(client: FlaskClient) -> None:
    """Test send endpoint with non-JSON body."""
    response = client.post("/send", data="not json", content_type="application/json")
    assert response.status_code == 400
    # Flask returns HTML error page for 400 by default, so json is None
    # We only verify status code here.


def test_send_missing_fields(client: FlaskClient) -> None:
    """Test send endpoint with missing fields."""
    response = client.post("/send", json={"title": "No Link"})
    assert response.status_code == 400
    assert response.json is not None
    assert "Invalid request" in response.json["message"]


def test_send_extraction_failure(client: FlaskClient) -> None:
    """Test handling of magnet extraction failures."""
    with patch("audiobook_automated.routes.extract_magnet_link") as mock_extract:
        mock_extract.return_value = (None, "Page Not Found")
        response = client.post(
            "/send",
            json={"link": "https://audiobookbay.lu/bad-page", "title": "Bad Book"},
        )
        # Updated to 400 because "Page Not Found" does not contain lowercase "found"
        assert response.status_code == 400
        assert response.json is not None
        assert "Download failed" in response.json["message"]


def test_send_connection_error(client: FlaskClient) -> None:
    """Test handling of connection errors during send."""
    with patch("audiobook_automated.routes.extract_magnet_link", side_effect=ConnectionError("Down")):
        response = client.post(
            "/send",
            json={"link": "https://audiobookbay.lu/book", "title": "Book"},
        )
        # Without specific handler, it falls through to generic 500 handler
        assert response.status_code == 500
        assert response.json is not None
        assert "Down" in response.json["message"]


def test_delete_success(client: FlaskClient) -> None:
    """Test successful torrent deletion."""
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        response = client.post("/delete", json={"id": "hash123"})
        assert response.status_code == 200
        mock_tm.remove_torrent.assert_called_with("hash123")


def test_delete_missing_id(client: FlaskClient) -> None:
    """Test delete endpoint without ID."""
    response = client.post("/delete", json={})
    assert response.status_code == 400


def test_reload_library_success(client: FlaskClient) -> None:
    """Test successful library scan trigger."""
    # Ensure config is set
    client.application.config["ABS_URL"] = "http://abs"
    client.application.config["ABS_KEY"] = "key"
    client.application.config["ABS_LIB"] = "lib"

    with patch("audiobook_automated.routes.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        response = client.post("/reload_library")
        assert response.status_code == 200
        assert response.json is not None
        assert "scan initiated" in response.json["message"]


def test_status_json(client: FlaskClient) -> None:
    """Test status endpoint returning JSON."""
    mock_status = [{"id": "1", "name": "Book", "progress": 50.0}]
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = mock_status
        response = client.get("/status?json=1")
        assert response.status_code == 200
        assert response.json == mock_status


def test_send_sanitization_warning(client: FlaskClient, caplog: Any) -> None:
    """Test logging warning for titles requiring sanitization fallback."""
    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        # FIX: Removed unused 'as mock_tm' to satisfy Ruff
        with patch("audiobook_automated.routes.torrent_manager"):
            client.post("/send", json={"link": "http://example.com", "title": "..."})
            # Updated expectation to match the new log message format in routes.py
            assert "required fallback/truncate handling" in caplog.text
            assert "Using collision-safe directory name" in caplog.text


@pytest.fixture
def csrf_app() -> Generator[Flask]:
    """Fixture creating an app with CSRF protection explicitly ENABLED.

    Overrides the default test config which disables CSRF.
    """
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "SAVE_PATH_BASE": "/tmp/test_security",
            "SECRET_KEY": "test-security-secret",
            "WTF_CSRF_ENABLED": True,  # CRITICAL: Enable CSRF for this suite
        }
    )
    yield app


def test_search_page_renders_csrf_token(csrf_app: Flask) -> None:
    """Ensure the search page template actually includes the CSRF meta tag.

    This confirms that the frontend has the necessary token to perform actions.
    """
    client = csrf_app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    # Check for the meta tag that actions.js reads
    assert b'name="csrf-token"' in response.data


def test_send_endpoint_requires_csrf(csrf_app: Flask) -> None:
    """Ensure the API rejects POST requests that lack the CSRF token.

    Simulates a CSRF attack or a broken frontend client.
    """
    client = csrf_app.test_client()
    # Attempt a POST request without headers/token
    response = client.post("/send", json={"link": "http://example.com", "title": "Test"})

    # Should fail with 400 Bad Request (The CSRF token is missing)
    assert response.status_code == 400
    assert b"The CSRF token is missing" in response.data or b"CSRF token missing" in response.data


def test_delete_endpoint_requires_csrf(csrf_app: Flask) -> None:
    """Ensure the Delete endpoint is protected against CSRF."""
    client = csrf_app.test_client()
    response = client.post("/delete", json={"id": "123"})
    assert response.status_code == 400


def test_reload_library_endpoint_requires_csrf(csrf_app: Flask) -> None:
    """Ensure the Library Reload endpoint is protected."""
    client = csrf_app.test_client()
    response = client.post("/reload_library")
    assert response.status_code == 400


def test_send_json_list(client: FlaskClient) -> None:
    """Test send endpoint with JSON list (not dict)."""
    response = client.post("/send", json=["not", "a", "dict"])
    assert response.status_code == 400
    assert response.json is not None
    assert "Invalid JSON format" in response.json["message"]


def test_send_invalid_title_type(client: FlaskClient) -> None:
    """Test send endpoint with a non-string title to ensure type safety."""
    # This prevents the 500 error where .strip() would be called on an int
    response = client.post("/send", json={"title": 12345, "link": "http://example.com/book"})
    assert response.status_code == 400
    assert response.json is not None
    assert "Title must be a string" in response.json["message"]


def test_send_deep_path_truncation(client: FlaskClient) -> None:
    """Test that extremely long paths are safely truncated."""
    # Simulate a user with a very deep SAVE_PATH_BASE (250 chars)
    # 260 limit - 250 base - 1 sep = 9 chars left.
    # Logic should enforce safety.
    deep_path = "/a/" * 83 + "a"  # ~250 chars
    client.application.config["SAVE_PATH_BASE"] = deep_path

    long_title = "A" * 100  # Should be heavily truncated

    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
            response = client.post("/send", json={"link": "http://link", "title": long_title})
            assert response.status_code == 200

            # Verify add_magnet was called with a path that respects the limit.
            # We expect the save_path to be joined with a truncated title.
            args, _ = mock_tm.add_magnet.call_args
            save_path = args[1]

            # The title component (basename) should be very short (~5-9 chars)
            base_name = os.path.basename(save_path)
            assert len(base_name) < 20
            assert len(base_name) >= 5  # Minimum floor check
            assert len(save_path) < 270  # Ensure we didn't explode the path length


def test_delete_json_list(client: FlaskClient) -> None:
    """Test delete endpoint with JSON list (not dict)."""
    response = client.post("/delete", json=["not", "a", "dict"])
    assert response.status_code == 400
    assert response.json is not None
    assert "Invalid JSON format" in response.json["message"]


def test_delete_exception(client: FlaskClient) -> None:
    """Test delete endpoint handling exceptions."""
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.remove_torrent.side_effect = Exception("Delete failed")
        response = client.post("/delete", json={"id": "123"})
        assert response.status_code == 500
        assert response.json is not None
        assert "Delete failed" in response.json["message"]


def test_reload_library_missing_config(client: FlaskClient) -> None:
    """Test reload_library with missing configuration."""
    # Ensure config is missing
    client.application.config["ABS_URL"] = None

    response = client.post("/reload_library")
    assert response.status_code == 400
    assert response.json is not None
    assert "not configured" in response.json["message"]


def test_reload_library_request_exception(client: FlaskClient) -> None:
    """Test reload_library handling request exceptions."""
    # Setup valid config so we reach the request part
    client.application.config["ABS_URL"] = "http://abs"
    client.application.config["ABS_KEY"] = "key"
    client.application.config["ABS_LIB"] = "lib"

    # Patch requests to raise exception
    import requests

    with patch(
        "audiobook_automated.routes.requests.post", side_effect=requests.exceptions.RequestException("ABS Down")
    ):
        response = client.post("/reload_library")
        assert response.status_code == 500
        assert response.json is not None
        assert "ABS Down" in response.json["message"]


def test_reload_library_request_exception_with_response(client: FlaskClient) -> None:
    """Test reload_library handling request exceptions with response detail."""
    client.application.config["ABS_URL"] = "http://abs"
    client.application.config["ABS_KEY"] = "key"
    client.application.config["ABS_LIB"] = "lib"

    from unittest.mock import Mock

    import requests

    mock_resp = Mock()
    mock_resp.status_code = 503
    mock_resp.reason = "Service Unavailable"
    mock_resp.text = "Maintenance"

    err = requests.exceptions.RequestException("ABS Down")
    err.response = mock_resp

    with patch("audiobook_automated.routes.requests.post", side_effect=err):
        response = client.post("/reload_library")
        assert response.status_code == 500
        assert response.json is not None
        assert "503 Service Unavailable: Maintenance" in response.json["message"]


def test_send_no_save_path_base(client: FlaskClient) -> None:
    """Test send endpoint when SAVE_PATH_BASE is not configured."""
    client.application.config["SAVE_PATH_BASE"] = None

    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
            response = client.post("/send", json={"link": "http://link", "title": "Book"})
            assert response.status_code == 200
            # Verify add_magnet was called with just the title (no base path)
            mock_tm.add_magnet.assert_called_with("magnet:?xt=urn:btih:123", "Book")
