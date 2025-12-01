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
    monkeypatch.setenv("DOWNLOAD_CLIENT", "qbittorrent")
    with patch("app.clients.QbClient") as MockQb:
        MockQb.return_value.auth_log_in.side_effect = LoginFailed("Bad Auth")
        manager = TorrentManager()
        assert manager._get_client() is None


def test_unsupported_client_type(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "unknown_client")
    manager = TorrentManager()
    assert manager._get_client() is None


def test_add_magnet_reconnect_retry(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "qbittorrent")
    with patch("app.clients.QbClient"):
        manager = TorrentManager()
        # Patch the logic method to throw then succeed
        with patch.object(manager, "_add_magnet_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), None]
            manager.add_magnet("magnet:...", "/save")
            assert mock_logic.call_count == 2
            assert manager._client is None


def test_get_status_reconnect(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "qbittorrent")
    with patch("app.clients.QbClient"):
        manager = TorrentManager()
        with patch.object(manager, "_get_status_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), []]
            result = manager.get_status()
            assert mock_logic.call_count == 2
            assert result == []
            assert manager._client is None


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


def test_format_size_edge_cases():
    tm = TorrentManager
    assert tm._format_size("not-a-number") == "N/A"
    assert tm._format_size([1, 2]) == "N/A"
    assert tm._format_size(None) == "N/A"

    # 5 Petabytes = 5 * 1024^5 bytes
    # Previous failure was because 1024*1024*1024*1024*5 is 5 TB, not 5 PB
    huge_number = 1024 * 1024 * 1024 * 1024 * 1024 * 5
    assert "5.00 PB" in tm._format_size(huge_number)


def test_deluge_add_magnet_label_error(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "delugeweb")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.add_torrent_magnet.side_effect = [Exception("Unknown parameter 'label'"), None]
        manager = TorrentManager()
        manager._add_magnet_logic("magnet:...", "/path")
        assert mock_instance.add_torrent_magnet.call_count == 2


def test_deluge_add_magnet_generic_error(monkeypatch):
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


def test_verify_credentials_fail(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "qbittorrent")
    with patch("app.clients.TorrentManager._get_client", return_value=None):
        manager = TorrentManager()
        assert manager.verify_credentials() is False


def test_logic_methods_no_client(monkeypatch):
    """Test that logic methods raise ConnectionError when client is None."""
    manager = TorrentManager()
    # Force client to be None despite any init attempts
    with patch.object(manager, "_get_client", return_value=None):
        with pytest.raises(ConnectionError):
            manager._add_magnet_logic("magnet:...", "/path")

        with pytest.raises(ConnectionError):
            manager._get_status_logic()
