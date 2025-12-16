"""Unit tests for QbittorrentStrategy."""

from unittest.mock import MagicMock, patch

import pytest

from audiobook_automated.clients.qbittorrent import Strategy as QbittorrentStrategy


def test_qbittorrent_strategy_add_magnet() -> None:
    """Test that QbittorrentStrategy adds magnet correctly."""
    with patch("audiobook_automated.clients.qbittorrent.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        mock_instance.torrents_add.return_value = "Ok."

        # Instantiate strategy directly to test implementation details
        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:123", "/downloads/Book", "audiobooks")

        MockQbClient.assert_called_with(
            host="localhost",
            port=8080,
            username="admin",
            password="admin",
            REQUESTS_ARGS={"timeout": 30},
        )
        mock_instance.auth_log_in.assert_called_once()
        mock_instance.torrents_add.assert_called_with(
            urls="magnet:?xt=urn:btih:123", save_path="/downloads/Book", category="audiobooks"
        )


def test_qbittorrent_add_magnet_failure_response() -> None:
    """Test logging when qBittorrent returns a failure string."""
    with patch("audiobook_automated.clients.qbittorrent.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        mock_instance.torrents_add.return_value = "Fails."

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        with patch("audiobook_automated.clients.qbittorrent.logger") as mock_logger:
            strategy.add_magnet("magnet:?xt=urn:btih:123", "/downloads/Book", "audiobooks")
            args, _ = mock_logger.warning.call_args
            assert "qBittorrent returned failure response" in args[0]
            assert "Fails." in args[0]


def test_remove_torrent_qbittorrent() -> None:
    """Test removing torrent for qBittorrent."""
    with patch("audiobook_automated.clients.qbittorrent.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("hash123")

        mock_instance.torrents_delete.assert_called_with(torrent_hashes="hash123", delete_files=False)


def test_get_status_qbittorrent() -> None:
    """Test fetching status from qBittorrent."""
    with patch("audiobook_automated.clients.qbittorrent.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value

        mock_torrent = MagicMock()
        mock_torrent.hash = "hash1"
        mock_torrent.name = "Test Book"
        mock_torrent.progress = 0.5
        mock_torrent.state = "downloading"
        mock_torrent.total_size = 1048576  # 1 MB

        mock_instance.torrents_info.return_value = [mock_torrent]

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0]["name"] == "Test Book"
        assert results[0]["progress"] == 50.0
        assert results[0]["size"] == "1.00 MB"


def test_get_status_qbittorrent_robustness() -> None:
    """Test qBittorrent handling of None progress."""
    with patch("audiobook_automated.clients.qbittorrent.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value

        mock_torrent = MagicMock()
        mock_torrent.hash = "hash_bad"
        mock_torrent.name = "Stalled Book"
        mock_torrent.progress = None
        mock_torrent.state = "metaDL"
        mock_torrent.total_size = None

        mock_instance.torrents_info.return_value = [mock_torrent]

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "Unknown"


def test_qbittorrent_close() -> None:
    """Test closing the qBittorrent session."""
    with patch("audiobook_automated.clients.qbittorrent.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        # Ensure client is set
        assert strategy.client is not None

        # Perform close
        strategy.close()

        # Verify logout called and client cleared
        mock_instance.auth_log_out.assert_called_once()
        assert strategy.client is None


def test_qbittorrent_close_exception() -> None:
    """Test exception handling during close."""
    with patch("audiobook_automated.clients.qbittorrent.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        # Simulate error on logout
        mock_instance.auth_log_out.side_effect = Exception("Logout Error")

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        with patch("audiobook_automated.clients.qbittorrent.logger") as mock_logger:
            strategy.close()
            # Should log debug but not raise
            mock_logger.debug.assert_called()
            assert "Error closing qBittorrent connection" in str(mock_logger.debug.call_args)

        # Client should still be cleared
        assert strategy.client is None


def test_strategy_not_connected_error_handling() -> None:
    """Ensure strategies raise ConnectionError if their client is None."""
    qb = QbittorrentStrategy("host", 80, "u", "p")
    with pytest.raises(ConnectionError, match="qBittorrent client not connected"):
        qb.add_magnet("m", "p", "c")
    with pytest.raises(ConnectionError, match="qBittorrent client not connected"):
        qb.remove_torrent("123")
    with pytest.raises(ConnectionError, match="qBittorrent client not connected"):
        qb.get_status("c")
