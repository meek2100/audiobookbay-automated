from unittest.mock import MagicMock, patch

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

        # Simulate exception when adding with label, then success without
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
    """Test that unsupported clients return None and log error instead of crashing."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "fake_client")
    manager = TorrentManager()

    # The manager catches the ValueError internally and returns None
    # This prevents the app from crashing on boot.
    client = manager._get_client()
    assert client is None


def test_format_size_logic():
    """Verify that bytes are converted to human-readable strings correctly."""
    # We can access the static method via the class
    tm = TorrentManager
    assert tm._format_size(500) == "500.00 B"
    assert tm._format_size(1024) == "1.00 KB"
    assert tm._format_size(1048576) == "1.00 MB"
    assert tm._format_size(1073741824) == "1.00 GB"
    assert tm._format_size(None) == "N/A"
    assert tm._format_size("not a number") == "N/A"


def test_remove_torrent_qbittorrent(mock_env):
    """Test removing torrent for qBittorrent."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        manager = TorrentManager()
        manager.remove_torrent("hash123")

        mock_instance.torrents_delete.assert_called_with(torrent_hashes="hash123", delete_files=False)


def test_remove_torrent_transmission(mock_env, monkeypatch):
    """Test removing torrent for Transmission."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "transmission")
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        manager = TorrentManager()

        # Test string ID (hash)
        manager.remove_torrent("hash123")
        mock_instance.remove_torrent.assert_called_with(ids=["hash123"], delete_data=False)


def test_remove_torrent_deluge(mock_env, monkeypatch):
    """Test removing torrent for Deluge."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "delugeweb")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        manager = TorrentManager()

        manager.remove_torrent("hash123")
        mock_instance.remove_torrent.assert_called_with("hash123", remove_data=False)


def test_get_status_qbittorrent(mock_env):
    """Test fetching status from qBittorrent."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value

        # Mock the torrent object returned by the library
        mock_torrent = MagicMock()
        mock_torrent.hash = "hash1"
        mock_torrent.name = "Test Book"
        mock_torrent.progress = 0.5
        mock_torrent.state = "downloading"
        mock_torrent.total_size = 1048576  # 1 MB

        mock_instance.torrents_info.return_value = [mock_torrent]

        manager = TorrentManager()
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["name"] == "Test Book"
        assert results[0]["progress"] == 50.0
        assert results[0]["size"] == "1.00 MB"


def test_get_status_transmission(mock_env, monkeypatch):
    """Test fetching status from Transmission."""
    monkeypatch.setenv("DOWNLOAD_CLIENT", "transmission")
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        mock_torrent = MagicMock()
        mock_torrent.id = 1
        mock_torrent.name = "Test Book"
        mock_torrent.progress = 0.75
        mock_torrent.status = "downloading"
        mock_torrent.total_size = 1024

        mock_instance.get_torrents.return_value = [mock_torrent]

        manager = TorrentManager()
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["progress"] == 75.0
        assert results[0]["size"] == "1.00 KB"
