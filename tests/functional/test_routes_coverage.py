"""Tests to ensure 100% coverage for routes.py."""

import os
from unittest.mock import patch

from flask.testing import FlaskClient


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
