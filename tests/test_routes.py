from unittest.mock import patch


def test_home_page_load(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Search AudiobookBay" in response.data


def test_csrf_protection_missing(client):
    """Ensure sending data without a CSRF token fails (Security Check)"""
    response = client.post("/send", json={"link": "http://example.com", "title": "Test"})
    # Flask-WTF usually returns 400 for CSRF errors
    assert response.status_code == 400


def test_status_page(client):
    with patch("app.app.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = [{"name": "Book 1", "progress": 50, "state": "Downloading", "size": "100 MB"}]
        response = client.get("/status")
        assert response.status_code == 200
        assert b"Book 1" in response.data
