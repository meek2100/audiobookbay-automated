# tests/functional/test_routes_coverage.py
"""Tests to ensure 100% coverage for routes.py."""

from unittest.mock import patch

from flask.testing import FlaskClient


def test_send_json_list(client: FlaskClient) -> None:
    """Test send endpoint with JSON list (not dict)."""
    response = client.post("/send", json=["not", "a", "dict"])
    assert response.status_code == 400
    assert response.json is not None
    assert "Invalid JSON format" in response.json["message"]


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
