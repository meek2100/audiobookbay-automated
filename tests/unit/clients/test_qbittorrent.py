# File: tests/unit/clients/test_qbittorrent.py
"""Unit tests for QbittorrentStrategy."""

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from audiobook_automated.clients.qbittorrent import Strategy as QbittorrentStrategy


def test_qbittorrent_add_magnet(app: Flask) -> None:
    """Test QbittorrentStrategy add_magnet."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        # Explicitly set config for test
        from flask import current_app

        current_app.config["CLIENT_TIMEOUT"] = 30

        mock_instance = MockQbClient.return_value
        # Mock add return (modern API returns JSON/Dict usually)
        mock_instance.torrents_add.return_value = "Ok."

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:ABC", "/downloads/Book", "audiobooks")

        mock_instance.auth_log_in.assert_called_once()
        mock_instance.torrents_add.assert_called_with(
            urls="magnet:?xt=urn:btih:ABC",
            save_path="/downloads/Book",
            category="audiobooks",
        )


def test_qbittorrent_add_magnet_legacy_fail(app: Flask) -> None:
    """Test that qBittorrent legacy 'Fails.' response raises ConnectionError."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        from flask import current_app

        current_app.config["CLIENT_TIMEOUT"] = 30

        mock_instance = MockQbClient.return_value
        mock_instance.torrents_add.return_value = "Fails."

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        with pytest.raises(ConnectionError, match="qBittorrent returned failure response: Fails."):
            strategy.add_magnet("magnet:...", "/path", "cat")


def test_remove_torrent_qbittorrent(app: Flask) -> None:
    """Test removing torrent for qBittorrent."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        from flask import current_app

        current_app.config["CLIENT_TIMEOUT"] = 30

        mock_instance = MockQbClient.return_value

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("hash123")

        mock_instance.torrents_delete.assert_called_with(torrent_hashes="hash123", delete_files=False)


def test_get_status_qbittorrent(app: Flask) -> None:
    """Test fetching status from qBittorrent."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        from flask import current_app

        current_app.config["CLIENT_TIMEOUT"] = 30

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
        assert results[0].name == "Test Book"
        assert results[0].progress == 50.0
        assert results[0].state == "Downloading"
        assert results[0].size == "1.00 MB"


def test_qbittorrent_stalledup_maps_to_seeding(app: Flask) -> None:
    """Test that qBittorrent stalledUP status normalizes to Seeding."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        mock_instance = MockQbClient.return_value
        mock_torrent = MagicMock()
        mock_torrent.hash = "hash2"
        mock_torrent.name = "Completed Book"
        mock_torrent.progress = 1.0
        mock_torrent.state = "stalledUP"
        mock_torrent.total_size = 2097152

        mock_instance.torrents_info.return_value = [mock_torrent]

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0].state == "Seeding"
        assert results[0].progress == 100.0


def test_qbittorrent_close(app: Flask) -> None:
    """Test closing the qBittorrent strategy."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        from flask import current_app

        current_app.config["CLIENT_TIMEOUT"] = 30

        mock_instance = MockQbClient.return_value

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        assert strategy.client is not None

        strategy.close()
        mock_instance.auth_log_out.assert_called_once()
        assert strategy.client is None

        # Also test closing when client has an active _http_session
        strategy.connect()
        mock_session = MagicMock()
        mock_instance._http_session = mock_session
        strategy.close()
        mock_session.close.assert_called_once()
        assert strategy.client is None


def test_qbittorrent_close_exception(app: Flask) -> None:
    """Test closing qBittorrent with exception (should be swallowed/logged)."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        from flask import current_app

        current_app.config["CLIENT_TIMEOUT"] = 30

        mock_instance = MockQbClient.return_value
        mock_instance.auth_log_out.side_effect = Exception("Logout Failed")

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        with patch("audiobook_automated.clients.qbittorrent.logger") as mock_logger:
            strategy.close()
            mock_logger.debug.assert_called()
            assert "Error closing qBittorrent connection" in str(mock_logger.debug.call_args[0])

        assert strategy.client is None


def test_get_status_qbittorrent_robustness(app: Flask) -> None:
    """Test qBittorrent handling of None progress."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        from flask import current_app

        current_app.config["CLIENT_TIMEOUT"] = 30

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
        assert results[0].progress == 0.0
        assert results[0].size == "Unknown"


def test_qbittorrent_not_connected() -> None:
    """Test errors when client is not connected."""
    strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
    # Do NOT connect

    with pytest.raises(ConnectionError, match="qBittorrent client not connected"):
        strategy.add_magnet("magnet:...", "/path", "cat")

    with pytest.raises(ConnectionError, match="qBittorrent client not connected"):
        strategy.remove_torrent("123")

    with pytest.raises(ConnectionError, match="qBittorrent client not connected"):
        strategy.get_status("cat")


def test_qbittorrent_api_key_auth(app: Flask) -> None:
    """Test connecting using api_key parameter."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        mock_instance = MockQbClient.return_value
        mock_instance.app.version = "v5.3.0"

        strategy = QbittorrentStrategy("localhost", 8080, "meek2100", "", api_key="test_api_key")
        strategy.connect()
        assert strategy.api_key == "test_api_key"
        MockQbClient.assert_called_with(
            host="localhost",
            port=8080,
            username="meek2100",
            api_key="test_api_key",
            REQUESTS_ARGS={"timeout": 30},
        )
        assert strategy.client is not None
        strategy.close()
        assert strategy.client is None


def test_qbittorrent_password_prefixed_api_key(app: Flask) -> None:
    """Test using password starting with 'qbt_' as api_key."""
    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        mock_instance = MockQbClient.return_value
        mock_instance.app.version = "v5.3.0"

        strategy = QbittorrentStrategy("localhost", 8080, "meek2100", "qbt_abc123key")
        strategy.connect()
        assert strategy.api_key == "qbt_abc123key"
        MockQbClient.assert_called_with(
            host="localhost",
            port=8080,
            username="meek2100",
            api_key="qbt_abc123key",
            REQUESTS_ARGS={"timeout": 30},
        )


def test_qbittorrent_auth_failure_cooldown(app: Flask) -> None:
    """Test repeated auth failures triggering cooldown backoff."""
    from qbittorrentapi.exceptions import LoginFailed

    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        mock_instance = MockQbClient.return_value
        mock_instance.auth_log_in.side_effect = LoginFailed("Auth failed")

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "wrong_pass")

        # 1st failure
        with pytest.raises(ConnectionError, match="Incorrect username or password"):
            strategy.connect()
        assert strategy.consecutive_auth_failures == 1

        # 2nd failure
        with pytest.raises(ConnectionError, match="Incorrect username or password"):
            strategy.connect()
        assert strategy.consecutive_auth_failures == 2

        # 3rd failure triggers backoff
        with pytest.raises(ConnectionError, match="Incorrect username or password"):
            strategy.connect()
        assert strategy.consecutive_auth_failures == 3
        assert strategy.auth_cooldown_until > 0

        # 4th attempt should be blocked by cooldown without hitting server
        with pytest.raises(ConnectionError, match="authentication cooldown active"):
            strategy.connect()


def test_qbittorrent_ip_banned_detection(app: Flask) -> None:
    """Test handling IP banned Forbidden403Error."""
    from qbittorrentapi.exceptions import Forbidden403Error

    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        mock_instance = MockQbClient.return_value
        mock_instance.auth_log_in.side_effect = Forbidden403Error(
            "Your IP address has been banned after too many failed authentication attempts."
        )

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")

        with pytest.raises(ConnectionError, match="IP address banned"):
            strategy.connect()
        assert strategy.is_ip_banned is True

        # Subsequent attempts are instantly blocked
        with pytest.raises(ConnectionError, match="IP address is banned"):
            strategy.connect()


def test_qbittorrent_generic_forbidden(app: Flask) -> None:
    """Test handling generic Forbidden403Error."""
    from qbittorrentapi.exceptions import Forbidden403Error

    with (
        patch("audiobook_automated.clients.qbittorrent.QbClient", autospec=True) as MockQbClient,
        app.app_context(),
    ):
        mock_instance = MockQbClient.return_value
        mock_instance.auth_log_in.side_effect = Forbidden403Error("Access denied")

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")

        with pytest.raises(ConnectionError, match="Invalid API key or credentials"):
            strategy.connect()
        assert strategy.consecutive_auth_failures == 1
