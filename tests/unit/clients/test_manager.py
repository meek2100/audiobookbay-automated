"""Unit tests for TorrentManager."""

import importlib
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from audiobook_automated.clients import TorrentManager, TorrentStatus


def test_init_with_dl_url(app: Flask, setup_manager: Any) -> None:
    """Test that DL_URL takes precedence if provided directly."""
    manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://custom-url:1234", DL_HOST=None, DL_PORT=None)
    assert manager.dl_url == "http://custom-url:1234"


def test_init_dl_url_construction(app: Flask, setup_manager: Any) -> None:
    """Test construction of DL_URL from host and port."""
    manager = setup_manager(app, DL_CLIENT="deluge", DL_URL=None, DL_HOST="myhost", DL_PORT=9999, DL_SCHEME="https")
    assert manager.dl_url == "https://myhost:9999"


def test_init_dl_url_deluge_default(app: Flask, setup_manager: Any) -> None:
    """Test default DL_URL for Deluge when host/port missing."""
    with patch("audiobook_automated.clients.manager.logger") as mock_logger:
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL=None, DL_HOST=None, DL_PORT=None)
        assert manager.dl_url == "http://localhost:8112"
        mock_logger.warning.assert_called_with("DL_HOST missing. Defaulting Deluge URL to localhost:8112.")


def test_init_dl_port_missing(app: Flask, setup_manager: Any) -> None:
    """Test that default port is assigned if DL_HOST is present but DL_PORT is missing."""
    with patch("audiobook_automated.clients.manager.logger") as mock_logger:
        # Case 1: Deluge -> 8112
        manager = setup_manager(app, DL_CLIENT="deluge", DL_HOST="deluge-host", DL_PORT=None)
        assert manager.port == 8112
        assert manager.dl_url == "http://deluge-host:8112"
        mock_logger.info.assert_called_with("DL_PORT missing. Defaulting to 8112 for deluge.")

        # Case 2: Other (qBittorrent) -> 8080
        manager_qb = setup_manager(app, DL_CLIENT="qbittorrent", DL_HOST="qb-host", DL_PORT=None)
        assert manager_qb.port == 8080
        assert manager_qb.dl_url == "http://qb-host:8080"


def test_init_dl_url_parse_failure(app: Flask, setup_manager: Any) -> None:
    """Test that init_app handles URL parsing exceptions gracefully."""
    with (
        patch("audiobook_automated.clients.manager.urlparse") as mock_parse,
        patch("audiobook_automated.clients.manager.logger") as mock_logger,
    ):
        mock_parse.side_effect = ValueError("Parsing boom")
        setup_manager(app, DL_URL="http://malformed")
        mock_logger.warning.assert_called()
        args, _ = mock_logger.warning.call_args
        assert "Failed to parse DL_URL" in args[0]


def test_verify_credentials_success(app: Flask, setup_manager: Any) -> None:
    """Targets verify_credentials success path (True)."""
    manager = setup_manager(app)
    # Mock _get_strategy to return a mock object (truthy)
    with patch.object(manager, "_get_strategy", return_value=MagicMock()):
        assert manager.verify_credentials() is True


def test_verify_credentials_failure(app: Flask, setup_manager: Any) -> None:
    """Targets verify_credentials failure path (False)."""
    manager = setup_manager(app)
    # Mock _get_strategy to return None
    with patch.object(manager, "_get_strategy", return_value=None):
        assert manager.verify_credentials() is False


def test_unsupported_client_strategy(app: Flask, setup_manager: Any) -> None:
    """Test that unsupported clients return None and log error instead of crashing."""
    manager = setup_manager(app, DL_CLIENT="fake_client")

    with patch("audiobook_automated.clients.manager.logger") as mock_logger:
        strategy = manager._get_strategy()
        assert strategy is None
        assert mock_logger.error.called
        args, _ = mock_logger.error.call_args
        # Should catch ImportError/ModuleNotFoundError
        assert "Unsupported download client configured or missing plugin" in args[0]


def test_get_strategy_missing_client_config(app: Flask, setup_manager: Any) -> None:
    """Test that missing DL_CLIENT logs error and returns None."""
    manager = TorrentManager()
    manager.init_app(app)
    manager.client_type = None  # Force None

    with patch("audiobook_automated.clients.manager.logger") as mock_logger:
        strategy = manager._get_strategy()
        assert strategy is None
        mock_logger.error.assert_called_with("DL_CLIENT not configured.")


def test_get_strategy_init_exception(app: Flask, setup_manager: Any) -> None:
    """Test that general exception during strategy init is caught."""
    manager = setup_manager(app, DL_CLIENT="qbittorrent")

    # We want import_module to fail ONLY when importing the client module.
    # Otherwise pytest/patch/logger imports will fail.
    original_import = importlib.import_module

    def side_effect(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == ".qbittorrent" or name == "audiobook_automated.clients.qbittorrent":
            raise Exception("Unexpected Error")
        return original_import(name, *args, **kwargs)

    with patch("importlib.import_module", side_effect=side_effect):
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            strategy = manager._get_strategy()
            assert strategy is None
            args, _ = mock_logger.error.call_args
            assert "Error initializing torrent client strategy" in args[0]


def test_get_strategy_missing_class(app: Flask, setup_manager: Any) -> None:
    """Test that missing Strategy class in module logs AttributeError."""
    manager = setup_manager(app, DL_CLIENT="qbittorrent")

    # We want import_module to fail ONLY when importing the client module.
    original_import = importlib.import_module
    mock_module = MagicMock(spec=[])

    def side_effect(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == ".qbittorrent" or name == "audiobook_automated.clients.qbittorrent":
            return mock_module
        return original_import(name, *args, **kwargs)

    with patch("importlib.import_module", side_effect=side_effect):
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            strategy = manager._get_strategy()
            assert strategy is None
            args, _ = mock_logger.error.call_args
            assert "does not export a 'Strategy' class" in args[0]


def test_remove_torrent_no_client_raises(app: Flask, setup_manager: Any) -> None:
    """Test that an error is raised if no client can be connected during removal."""
    manager = setup_manager(app)
    with patch.object(manager, "_get_strategy", return_value=None):
        with pytest.raises(ConnectionError) as exc:
            manager.remove_torrent("123")
        assert "Torrent client is not connected" in str(exc.value)


def test_remove_torrent_retry(app: Flask, setup_manager: Any) -> None:
    """Test that remove_torrent attempts to reconnect if the first call fails."""
    # We mock _get_strategy to return a strategy first, then None or a strategy that fails?
    # Actually, the test patches `_remove_torrent_logic`.
    manager = setup_manager(app)
    with patch.object(manager, "_remove_torrent_logic") as mock_logic:
        mock_logic.side_effect = [Exception("Stale Connection"), None]
        manager.remove_torrent("hash123")
        assert mock_logic.call_count == 2
        # THREAD SAFETY UPDATE: Checked threaded local instead of _client
        assert getattr(manager._local, "strategy", None) is None


def test_add_magnet_reconnect_retry(app: Flask, setup_manager: Any) -> None:
    """Test that add_magnet attempts to reconnect if the first call fails."""
    manager = setup_manager(app)
    # Patch the logic method to throw then succeed
    with patch.object(manager, "_add_magnet_logic") as mock_logic:
        mock_logic.side_effect = [Exception("Stale Connection"), None]
        manager.add_magnet("magnet:...", "/save")
        assert mock_logic.call_count == 2
        # THREAD SAFETY UPDATE: Checked threaded local instead of _client
        assert getattr(manager._local, "strategy", None) is None


def test_logic_methods_no_client(app: Flask, setup_manager: Any) -> None:
    """Test that logic methods raise ConnectionError when strategy is None."""
    manager = setup_manager(app)
    # Force client to be None despite any init attempts
    with patch.object(manager, "_get_strategy", return_value=None):
        with pytest.raises(ConnectionError):
            manager._add_magnet_logic("magnet:...", "/path")

        with pytest.raises(ConnectionError):
            manager._get_status_logic()


def test_remove_torrent_retry_coverage(app: Flask, setup_manager: Any) -> None:
    """Test retry logic in remove_torrent via mocked strategy."""
    manager = setup_manager(app)

    # Mock _get_strategy to fail first time (return None -> raises ConnectionError in logic)
    # Wait, remove_torrent calls _remove_torrent_logic.
    # _remove_torrent_logic calls _get_strategy.
    # If _remove_torrent_logic raises, remove_torrent sets strategy=None and retries.

    # So we patch _get_strategy to return S1 (fails), then S2 (succeeds).
    strategy_fail = MagicMock()
    strategy_fail.remove_torrent.side_effect = Exception("Fail")

    strategy_ok = MagicMock()

    with patch.object(manager, "_get_strategy", side_effect=[strategy_fail, strategy_ok]):
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            manager.remove_torrent("123")

            # Verify retry log
            assert mock_logger.warning.called
            assert "Attempting to reconnect" in str(mock_logger.warning.call_args[0][0])

            # First call fail
            strategy_fail.remove_torrent.assert_called_with("123")
            # Second call ok
            strategy_ok.remove_torrent.assert_called_with("123")


def test_get_status_retry_coverage(app: Flask, setup_manager: Any) -> None:
    """Test retry logic in get_status."""
    manager = setup_manager(app)

    strategy_mock = MagicMock()
    # Return a dict that matches TorrentStatus structure partially or cast it
    mock_status = cast(list[TorrentStatus], [{"name": "test"}])
    strategy_mock.get_status.return_value = mock_status

    with patch.object(manager, "_get_strategy") as mock_get_strat:
        mock_get_strat.side_effect = [None, strategy_mock]

        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            status = manager.get_status()

            assert len(status) == 1
            assert status[0]["name"] == "test"

            # Verify retry log
            assert mock_logger.warning.called
            assert "Reconnecting" in str(mock_logger.warning.call_args[0][0])

            assert mock_get_strat.call_count == 2
