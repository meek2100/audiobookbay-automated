from typing import Any
from unittest.mock import patch


def test_health_check_route(client: Any) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    assert response.content_type == "application/json"


def test_home_page_static_versioning(client: Any) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b"?v=" in response.data
    assert b"favicon.ico?v=" in response.data


def test_static_assets_cache_control(client: Any) -> None:
    response = client.get("/static/images/favicon.ico")
    if response.status_code == 200:
        cache_control = response.headers.get("Cache-Control", "")
        assert "max-age=31536000" in cache_control
        assert "public" in cache_control


def test_nav_link_injection(client: Any) -> None:
    """Test that injected variables correctly appear in the template."""
    # FIX: Update config directly on the app instance, not via module monkeypatch
    client.application.config["NAV_LINK_NAME"] = "My Player"
    client.application.config["NAV_LINK_URL"] = "http://player.local"

    response = client.get("/")
    assert b"My Player" in response.data
    assert b"http://player.local" in response.data


def test_status_page(client: Any) -> None:
    # FIX: Patch where it is imported in routes.py
    with patch("app.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = [{"name": "Book 1", "progress": 50, "state": "Downloading", "size": "100 MB"}]
        response = client.get("/status")
        assert response.status_code == 200
        assert b"Book 1" in response.data


def test_status_route_error(client: Any) -> None:
    with patch("app.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.side_effect = Exception("Database Locked")

        response = client.get("/status")
        assert response.status_code == 200
        assert b"Error connecting to client" in response.data
        assert b"Database Locked" in response.data


def test_status_page_empty(client: Any) -> None:
    """Test status page rendering when there are no active torrents.

    Ensures the empty state message matches the UI expectations.
    """
    with patch("app.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = []
        response = client.get("/status")
        assert response.status_code == 200
        assert b"No active downloads found" in response.data
