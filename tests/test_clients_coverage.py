from unittest.mock import MagicMock, patch

from app.clients import TorrentManager


def test_init_transmission_failure(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "transmission")
    monkeypatch.setenv("DL_HOST", "localhost")
    with patch("app.clients.TxClient") as MockTx:
        MockTx.side_effect = Exception("Connection refused")
        manager = TorrentManager()
        assert manager._get_client() is None


def test_init_deluge_failure(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "delugeweb")
    monkeypatch.setenv("DL_PASSWORD", "pass")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        MockDeluge.return_value.login.side_effect = Exception("Login failed")
        manager = TorrentManager()
        assert manager._get_client() is None


def test_add_magnet_reconnect_retry(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "qbittorrent")
    with patch("app.clients.QbClient") as MockQb:
        manager = TorrentManager()
        manager._client = MagicMock()
        manager._client.torrents_add.side_effect = Exception("Connection lost")
        manager.add_magnet("magnet:...", "/save")
        assert MockQb.call_count >= 1


def test_get_status_deluge(monkeypatch):
    """Test fetching status from Deluge client."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "delugeweb")

    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value

        # Mock the complex return structure of deluge-web-client
        mock_response = MagicMock()
        mock_response.result = {
            "hash123": {
                "name": "Deluge Book",
                "state": "Downloading",
                "progress": 45.5,
                "total_size": 1024 * 1024 * 100,  # 100 MB
            }
        }
        mock_instance.get_torrents_status.return_value = mock_response

        manager = TorrentManager()
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["name"] == "Deluge Book"
        assert results[0]["state"] == "Downloading"
        assert results[0]["size"] == "100.00 MB"
