from unittest.mock import patch


def test_health_check_route(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    assert response.content_type == "application/json"


def test_home_page_static_versioning(client):
    """
    Verify that static assets in the HTML are appended with the version hash.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert b"?v=" in response.data
    assert b"favicon.ico?v=" in response.data


def test_static_assets_cache_control(client):
    """
    Verify that static files are served with a long cache duration (1 year).
    """
    response = client.get("/static/images/favicon.ico")
    if response.status_code == 200:
        cache_control = response.headers.get("Cache-Control", "")
        assert "max-age=31536000" in cache_control
        assert "public" in cache_control


def test_nav_link_injection(client, monkeypatch, app_module):
    """Test that injected variables correctly appear in the template."""
    monkeypatch.setattr(app_module, "NAV_LINK_NAME", "My Player")
    monkeypatch.setattr(app_module, "NAV_LINK_URL", "http://player.local")
    response = client.get("/")
    assert b"My Player" in response.data
    assert b"http://player.local" in response.data


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
