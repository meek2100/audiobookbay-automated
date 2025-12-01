from unittest.mock import patch

import pytest

from app.clients import TorrentManager


@pytest.fixture
def mock_env(monkeypatch):
    """Sets up default environment variables for testing."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "qbittorrent")
    monkeypatch.setenv("DL_HOST", "localhost")
    monkeypatch.setenv("DL_PORT", "8080")
    monkeypatch.setenv("DL_USERNAME", "admin")
    monkeypatch.setenv("DL_PASSWORD", "admin")
    monkeypatch.setenv("DL_CATEGORY", "audiobooks")


def test_qbittorrent_add_magnet(mock_env):
    with patch("app.clients.QbClient") as MockQbClient:
        # Setup the mock client instance
        mock_instance = MockQbClient.return_value

        manager = TorrentManager()
        # Trigger the lazy loading of the client
        manager._get_client()

        manager.add_magnet("magnet:?xt=urn:btih:123", "/downloads/Book")

        # Verify login was called
        mock_instance.auth_log_in.assert_called_once()
        # Verify add torrent was called with correct args
        mock_instance.torrents_add.assert_called_with(
            urls="magnet:?xt=urn:btih:123", save_path="/downloads/Book", category="audiobooks"
        )


def test_transmission_add_magnet(mock_env, monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "transmission")

    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        manager = TorrentManager()
        manager.add_magnet("magnet:?xt=urn:btih:ABC", "/downloads/Book")

        mock_instance.add_torrent.assert_called_with(
            "magnet:?xt=urn:btih:ABC", download_dir="/downloads/Book", labels=["audiobooks"]
        )


def test_deluge_add_magnet(mock_env, monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "delugeweb")

    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value

        manager = TorrentManager()
        manager.add_magnet("magnet:?xt=urn:btih:XYZ", "/downloads/Book")

        mock_instance.login.assert_called_once()
        mock_instance.add_torrent_magnet.assert_called_with(
            "magnet:?xt=urn:btih:XYZ", save_directory="/downloads/Book", label="audiobooks"
        )


def test_deluge_label_plugin_error(mock_env, monkeypatch):
    """Test that Deluge falls back to adding torrent without label if plugin is missing."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "delugeweb")

    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value

        # Simulate exception when adding with label
        mock_instance.add_torrent_magnet.side_effect = [
            Exception("Unknown parameter 'label'"),  # First call fails
            None,  # Second call (without label) succeeds
        ]

        manager = TorrentManager()
        manager.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book")

        # Verify it was called twice
        assert mock_instance.add_torrent_magnet.call_count == 2

        # Check call arguments
        # 1. First attempt with label
        mock_instance.add_torrent_magnet.assert_any_call(
            "magnet:?xt=urn:btih:FAIL", save_directory="/downloads/Book", label="audiobooks"
        )
        # 2. Second attempt without label
        mock_instance.add_torrent_magnet.assert_any_call("magnet:?xt=urn:btih:FAIL", save_directory="/downloads/Book")


def test_unsupported_client(mock_env, monkeypatch):
    monkeypatch.setenv("DOWNLOAD_CLIENT", "fake_client")
    manager = TorrentManager()
    with pytest.raises(ValueError) as excinfo:
        manager._get_client()
    assert "Unsupported download client" in str(excinfo.value)
