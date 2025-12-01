from unittest.mock import MagicMock, patch

import pytest
from qbittorrentapi import LoginFailed

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


def test_init_qbittorrent_login_failed(monkeypatch):
    """Test specifically for LoginFailed exception."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "qbittorrent")
    with patch("app.clients.QbClient") as MockQb:
        MockQb.return_value.auth_log_in.side_effect = LoginFailed("Bad Auth")
        manager = TorrentManager()
        # The manager catches ALL exceptions and logs them
        assert manager._get_client() is None


def test_unsupported_client_type(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "unknown_client")
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
    monkeypatch.setenv("DOWNLOAD_CLIENT", "delugeweb")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        mock_response.result = {"hash123": {"name": "D Book", "state": "Dl", "progress": 45.5, "total_size": 100}}
        mock_instance.get_torrents_status.return_value = mock_response
        manager = TorrentManager()
        results = manager.get_status()
        assert len(results) == 1


def test_format_size_invalids():
    tm = TorrentManager
    assert tm._format_size("not-a-number") == "N/A"
    assert tm._format_size([1, 2]) == "N/A"


def test_deluge_add_magnet_label_error(monkeypatch):
    """Test Deluge label plugin missing logic."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "delugeweb")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value

        # FIX: First call raises exception, second call succeeds
        mock_instance.add_torrent_magnet.side_effect = [Exception("Unknown parameter 'label'"), None]

        manager = TorrentManager()
        manager._add_magnet_logic("magnet:...", "/path")

        # Verify it called add_torrent_magnet TWICE (once with label, once without)
        assert mock_instance.add_torrent_magnet.call_count == 2


def test_deluge_add_magnet_generic_error(monkeypatch):
    """Test Deluge generic error (NOT label related)."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "delugeweb")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.add_torrent_magnet.side_effect = Exception("Generic Failure")

        manager = TorrentManager()

        with pytest.raises(Exception) as exc:
            manager._add_magnet_logic("magnet:...", "/path")
        assert "Generic Failure" in str(exc.value)


def test_remove_torrent_no_client(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "transmission")
    with patch("app.clients.TxClient", side_effect=Exception("Down")):
        manager = TorrentManager()
        with pytest.raises(ConnectionError):
            manager.remove_torrent("123")


def test_get_status_reconnect(monkeypatch):
    """Test that get_status tries to reconnect on failure."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "qbittorrent")
    with patch("app.clients.QbClient") as MockQb:
        manager = TorrentManager()
        manager._client = MagicMock()
        manager._client.torrents_info.side_effect = Exception("Socket closed")

        MockQb.return_value.torrents_info.return_value = []

        manager.get_status()
        assert MockQb.call_count >= 1
