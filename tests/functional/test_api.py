from typing import Any
from unittest.mock import MagicMock, patch

import requests

from audiobook_automated.constants import FALLBACK_TITLE


def test_healthcheck(client: Any) -> None:
    """Ensure the healthcheck endpoint works."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_search_page_render(client: Any) -> None:
    """Test that the search page renders correctly (GET /)."""
    response = client.get("/")
    assert response.status_code == 200
    # Search page generally contains a search button or input
    assert b"Search" in response.data


def test_search_execution(client: Any) -> None:
    """Test that a search query triggers the scraper and renders results."""
    # Mock the scraper so we don't hit external sites
    with patch("audiobook_automated.routes.search_audiobookbay") as mock_search:
        mock_search.return_value = [
            {
                "title": "Mock Book",
                "link": "http://audiobookbay.lu/mock-book",
                "cover": "http://cover.jpg",
                "language": "English",
                "category": "Fiction",
                "post_date": "2025-01-01",
                "format": "MP3",
                "bitrate": "128 kbps",
                "file_size": "100 MB",
            }
        ]
        response = client.get("/?query=test")
        assert response.status_code == 200
        assert b"Mock Book" in response.data
        mock_search.assert_called_with("test")


def test_search_failure(client: Any) -> None:
    """Test search handling when the scraper raises an exception."""
    with patch("audiobook_automated.routes.search_audiobookbay") as mock_search:
        mock_search.side_effect = Exception("Scraping error")
        response = client.get("/?query=fail")
        assert response.status_code == 200  # Renders template with error
        assert b"Scraping error" in response.data


def test_details_page_render(client: Any) -> None:
    """Test that the details page renders correctly with valid data."""
    with patch("audiobook_automated.routes.get_book_details") as mock_details:
        mock_details.return_value = {
            "title": "Detailed Book",
            "description": "A great description",
            "trackers": ["http://tracker.com"],
            "file_size": "500 MB",
            "info_hash": "1234567890abcdef",
            "language": "English",
            "category": "Sci-Fi",
            "post_date": "2025-01-01",
            "format": "M4B",
            "bitrate": "64 kbps",
            "cover": "http://img.png",
            "author": "Author Name",
            "narrator": "Narrator Name",
            "link": "http://audiobookbay.lu/book",
        }
        response = client.get("/details?link=http://audiobookbay.lu/book")
        assert response.status_code == 200
        assert b"Detailed Book" in response.data
        assert b"A great description" in response.data


def test_details_missing_link(client: Any) -> None:
    """Test redirection when the 'link' parameter is missing."""
    response = client.get("/details")
    # Should redirect back to search
    assert response.status_code == 302
    assert response.location == "/"


def test_details_fetch_failure(client: Any) -> None:
    """Test details page handling when fetching details fails."""
    with patch("audiobook_automated.routes.get_book_details") as mock_details:
        mock_details.side_effect = Exception("Details fetch failed")
        response = client.get("/details?link=http://audiobookbay.lu/bad")
        assert response.status_code == 200
        assert b"Could not load details" in response.data
        assert b"Details fetch failed" in response.data


def test_send_success(client: Any) -> None:
    with (
        patch("audiobook_automated.routes.extract_magnet_link") as mock_extract,
        patch("audiobook_automated.routes.torrent_manager") as mock_tm,
    ):
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
        response = client.post("/send", json={"link": "https://audiobookbay.lu/book-page", "title": "Test Book"})
        assert response.status_code == 200
        mock_tm.add_magnet.assert_called_once()


def test_send_missing_data(client: Any) -> None:
    response = client.post("/send", json={"link": "http://example.com"})
    assert response.status_code == 400
    assert b"Invalid request" in response.data


def test_send_malformed_json(client: Any) -> None:
    response = client.post("/send", data="not json", content_type="application/json")
    assert response.status_code == 400


def test_send_invalid_json_type(client: Any) -> None:
    """Test that sending a List instead of a Dict to /send returns 400.

    Covers coverage gap in routes.py lines 122-123.
    """
    # Using json parameter ensures correct Content-Type and serialization
    response = client.post("/send", json=["not", "a", "dict"])
    assert response.status_code == 400
    assert response.json == {"message": "Invalid JSON format"}


def test_send_extraction_failure(client: Any) -> None:
    with patch("audiobook_automated.routes.extract_magnet_link") as mock_extract:
        mock_extract.return_value = (None, "Page Not Found")
        response = client.post("/send", json={"link": "https://audiobookbay.lu/bad-page", "title": "Bad Book"})
        assert response.status_code == 500
        assert b"Download failed: Page Not Found" in response.data


def test_send_torrent_client_failure(client: Any) -> None:
    with (
        patch("audiobook_automated.routes.extract_magnet_link") as mock_extract,
        patch("audiobook_automated.routes.torrent_manager") as mock_tm,
    ):
        mock_extract.return_value = ("magnet:?xt=urn:btih:123", None)
        mock_tm.add_magnet.side_effect = Exception("Connection Refused")
        response = client.post("/send", json={"link": "https://audiobookbay.lu/book-page", "title": "Test Book"})
        assert response.status_code == 500
        assert b"Connection Refused" in response.data


def test_send_route_no_save_path_base(client: Any) -> None:
    client.application.config["SAVE_PATH_BASE"] = None

    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:...", None)):
        with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
            response = client.post("/send", json={"link": "l", "title": "t"})
            assert response.status_code == 200
            mock_tm.add_magnet.assert_called_with("magnet:...", "t")


def test_send_sanitization_warning(client: Any, caplog: Any) -> None:
    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
            client.post("/send", json={"link": "http://example.com", "title": "..."})
            # FIX: Updated assert to match actual log message in routes.py
            assert f"Title '...' required fallback handling ('{FALLBACK_TITLE}')" in caplog.text
            args, _ = mock_tm.add_magnet.call_args
            assert FALLBACK_TITLE in args[1]


def test_send_fallback_title_uuid(client: Any) -> None:
    """Test that a title sanitizing to empty triggers UUID generation."""
    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
            # "..." sanitizes to "" which falls back to FALLBACK_TITLE
            client.post("/send", json={"link": "http://link", "title": "..."})

            assert mock_tm.add_magnet.called
            args, _ = mock_tm.add_magnet.call_args
            save_path = args[1]
            # Expect FALLBACK_TITLE + "_" (from UUID append)
            assert FALLBACK_TITLE in save_path
            assert "_" in save_path
            # It should be longer than just FALLBACK_TITLE due to UUID
            assert len(save_path) > len(FALLBACK_TITLE)


def test_send_windows_reserved_name(client: Any) -> None:
    """Test that reserved names (e.g., CON) trigger the collision-safe UUID logic.

    This ensures full coverage of the collision prevention logic in routes.py.
    """
    with patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:?xt=urn:btih:123", None)):
        with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
            # 'CON' -> sanitize_title returns 'CON_Safe' -> Triggers UUID logic in routes.py
            client.post("/send", json={"link": "http://link", "title": "CON"})

            # Verify that add_magnet was called with a path containing the _Safe suffix AND a UUID
            assert mock_tm.add_magnet.called
            args, _ = mock_tm.add_magnet.call_args
            save_path = args[1]
            assert "CON_Safe_" in save_path


def test_delete_torrent(client: Any) -> None:
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.remove_torrent.return_value = None
        response = client.post("/delete", json={"id": "hash123"})
        assert response.status_code == 200
        mock_tm.remove_torrent.assert_called_with("hash123")


def test_delete_torrent_missing_id(client: Any) -> None:
    response = client.post("/delete", json={})
    assert response.status_code == 400
    assert b"Torrent ID is required" in response.data


def test_delete_invalid_json_type(client: Any) -> None:
    """Test that sending a List instead of a Dict to /delete returns 400.

    Covers coverage gap in routes.py line 182.
    """
    response = client.post("/delete", json=["not", "a", "dict"])
    assert response.status_code == 400
    assert response.json == {"message": "Invalid JSON format"}


def test_delete_torrent_failure(client: Any) -> None:
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.remove_torrent.side_effect = Exception("Removal failed")
        response = client.post("/delete", json={"id": "hash123"})
        assert response.status_code == 500
        assert b"Removal failed" in response.data


def test_reload_library_success(client: Any) -> None:
    client.application.config["ABS_URL"] = "http://abs"
    client.application.config["ABS_KEY"] = "token"
    client.application.config["ABS_LIB"] = "lib-id"

    with patch("audiobook_automated.routes.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        response = client.post("/reload_library")
        assert response.status_code == 200
        assert b"scan initiated" in response.data


def test_reload_library_not_configured(client: Any) -> None:
    client.application.config["ABS_URL"] = None
    response = client.post("/reload_library")
    assert response.status_code == 400
    assert b"not configured" in response.data


def test_reload_library_detailed_error(client: Any) -> None:
    client.application.config["ABS_URL"] = "http://abs"
    client.application.config["ABS_KEY"] = "k"
    client.application.config["ABS_LIB"] = "l"

    with patch("audiobook_automated.routes.requests.post") as mock_post:
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


def test_status_page_html(client: Any) -> None:
    """Test the status page rendering via HTML."""
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = [
            {"id": "1", "name": "Book A", "progress": 10.0, "state": "DL", "size": "100 MB"}
        ]
        response = client.get("/status")
        assert response.status_code == 200
        assert b"Book A" in response.data


def test_status_page_json(client: Any) -> None:
    """Test the status page returning JSON (used by polling)."""
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = [
            {"id": "2", "name": "Book B", "progress": 50.0, "state": "DL", "size": "1 GB"}
        ]
        response = client.get("/status?json=1")
        assert response.status_code == 200
        assert response.json[0]["name"] == "Book B"


def test_status_page_failure_html(client: Any) -> None:
    """Test status page rendering error message on failure."""
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.side_effect = Exception("Client Error")
        response = client.get("/status")
        assert response.status_code == 200
        assert b"Error connecting to client" in response.data


def test_status_page_failure_json(client: Any) -> None:
    """Test status page returning JSON error on failure."""
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.side_effect = Exception("Client Error")
        response = client.get("/status?json=1")
        # JSON errors typically return 500
        assert response.status_code == 500
        assert response.json == {"error": "Client Error"}


def test_rate_limit_enforced(client: Any) -> None:
    # Ensure limiter is enabled (TestConfig already sets it)
    with (
        patch("audiobook_automated.routes.extract_magnet_link", return_value=("magnet:123", None)),
        patch("audiobook_automated.routes.torrent_manager"),
    ):
        for _ in range(60):
            response = client.post("/send", json={"link": "l", "title": "t"})
            assert response.status_code == 200

        response = client.post("/send", json={"link": "l", "title": "t"})
        assert response.status_code == 429
