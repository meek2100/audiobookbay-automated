# File: tests/unit/clients/test_manager.py
"""Unit tests for the TorrentManager."""

import importlib
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from audiobook_automated.clients import TorrentManager, TorrentStatus
from audiobook_automated.clients.base import TorrentClientStrategy


def test_init_with_dl_url(app: Flask, setup_manager: Any) -> None:
    """Test that DL_URL takes precedence if provided directly."""
    manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://custom-url:1234", DL_HOST=None, DL_PORT=None)
    assert manager.dl_url == "http://custom-url:1234"


def test_init_dl_url_construction(app: Flask, setup_manager: Any) -> None:
    """Test construction of DL_URL from host and port."""
    manager = setup_manager(
        app,
        DL_CLIENT="deluge",
        DL_URL=None,
        DL_HOST="myhost",
        DL_PORT=9999,
        DL_SCHEME="https",
    )
    assert manager.dl_url == "https://myhost:9999"


def test_init_dl_url_deluge_default(app: Flask, setup_manager: Any) -> None:
    """Test default DL_URL for Deluge when host/port missing."""
    with patch("audiobook_automated.clients.manager.logger") as mock_logger:
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL=None, DL_HOST=None, DL_PORT=None)
        assert manager.dl_url == "http://localhost:8112"
        mock_logger.warning.assert_called_with("DL_HOST missing. Defaulting Deluge to localhost.")


def test_init_dl_port_missing(app: Flask, setup_manager: Any) -> None:
    """Test that default port is assigned if DL_HOST is present but DL_PORT is missing."""
    # Mock loading the strategy class to return a default port (Simulating Deluge)
    mock_strategy = MagicMock()
    mock_strategy.DEFAULT_PORT = 8112

    with patch("audiobook_automated.clients.manager.TorrentManager._load_strategy_class", return_value=mock_strategy):
        manager = setup_manager(app, DL_CLIENT="deluge", DL_HOST="deluge-host", DL_PORT=None)
        assert manager.port == 8112
        assert manager.dl_url == "http://deluge-host:8112"


def test_init_app_strategy_load_exception(app: Flask, setup_manager: Any) -> None:
    """Test that exceptions during init_app strategy loading are caught and logged."""
    # This covers the 'except Exception' block in manager.py init_app logic
    with patch(
        "audiobook_automated.clients.manager.TorrentManager._load_strategy_class", side_effect=Exception("Init Boom")
    ):
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            setup_manager(app, DL_CLIENT="broken_init")
            mock_logger.debug.assert_called()
            # Verify the specific debug log format
            assert "Error checking default port" in mock_logger.debug.call_args[0][0]


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
        # The new logic in _load_strategy_class catches the ImportError and returns None,
        # so _get_strategy logs "Could not load strategy..."
        args, _ = mock_logger.error.call_args
        assert "Could not load strategy for client" in args[0]


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
    original_import = importlib.import_module

    def side_effect(name: str, *args: Any, **kwargs: Any) -> Any:
        # NOTE: Updated to match new package logic
        if name == ".qbittorrent" or name == "audiobook_automated.clients.qbittorrent":
            raise Exception("Unexpected Error")
        return original_import(name, *args, **kwargs)

    with patch("importlib.import_module", side_effect=side_effect):
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            strategy = manager._get_strategy()
            assert strategy is None
            args, _ = mock_logger.error.call_args
            assert "Error initializing torrent client strategy" in args[0]


def test_get_strategy_syntax_error(app: Flask, setup_manager: Any) -> None:
    """Test that SyntaxError in client plugin is caught and logged."""
    manager = setup_manager(app, DL_CLIENT="qbittorrent")

    original_import = importlib.import_module

    def side_effect(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == ".qbittorrent" or name == "audiobook_automated.clients.qbittorrent":
            raise SyntaxError("Bad syntax")
        return original_import(name, *args, **kwargs)

    with patch("importlib.import_module", side_effect=side_effect):
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            strategy = manager._get_strategy()
            assert strategy is None
            mock_logger.critical.assert_called()
            assert "Syntax Error in client plugin" in mock_logger.critical.call_args[0][0]


def test_get_strategy_missing_class(app: Flask, setup_manager: Any) -> None:
    """Test that missing Strategy class in module logs AttributeError."""
    manager = setup_manager(app, DL_CLIENT="qbittorrent")

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
            # Scan all error calls for the specific message
            found = False
            for call in mock_logger.error.call_args_list:
                if "does not export a 'Strategy' class" in call[0][0]:
                    found = True
                    break
            assert found, "Expected error message about missing Strategy class not found."


def test_get_strategy_caching_and_success(app: Flask, setup_manager: Any) -> None:
    """Test that strategy is initialized, cached, and reused."""
    manager = setup_manager(app, DL_CLIENT="mock_client")

    # MOCK FIX: Create a real dummy class to satisfy issubclass() checks
    class MockStrategy(TorrentClientStrategy):
        DEFAULT_PORT = 1234

        def connect(self) -> None:
            pass

        def close(self) -> None:
            pass

        def add_magnet(self, *args: Any) -> None:
            pass

        def remove_torrent(self, *args: Any) -> None:
            pass

        # FIX: Added explicit return type annotation to satisfy MyPy
        def get_status(self, *args: Any) -> list[TorrentStatus]:
            return []

    mock_module = MagicMock()
    mock_module.Strategy = MockStrategy

    with patch("importlib.import_module", return_value=mock_module) as mock_import:
        # 1. First Call: Should Initialize
        strategy1 = manager._get_strategy()
        assert strategy1 is not None
        assert isinstance(strategy1, MockStrategy)

        # 2. Second Call: Should use Cache
        # Reset mocks to prove they aren't called again
        mock_import.reset_mock()

        strategy2 = manager._get_strategy()
        assert strategy2 is strategy1
        mock_import.assert_not_called()


def test_remove_torrent_no_client_raises(app: Flask, setup_manager: Any) -> None:
    """Test that an error is raised if no client can be connected during removal."""
    manager = setup_manager(app)
    with patch.object(manager, "_get_strategy", return_value=None):
        with pytest.raises(ConnectionError) as exc:
            manager.remove_torrent("123")
        assert "Torrent client is not connected" in str(exc.value)


def test_add_magnet_success_logic(app: Flask, setup_manager: Any) -> None:
    """Test the happy path of add_magnet logic execution."""
    # Explicitly set category to match the assertion below
    manager = setup_manager(app, DL_CATEGORY="abb-automated")
    mock_strategy = MagicMock()

    with patch.object(manager, "_get_strategy", return_value=mock_strategy):
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            manager.add_magnet("magnet:?xt=urn:btih:123", "/downloads")

            # Verify Logger
            assert mock_logger.info.called
            args, _ = mock_logger.info.call_args
            assert "Adding torrent to" in args[0]

            # Verify Strategy Call
            mock_strategy.add_magnet.assert_called_with("magnet:?xt=urn:btih:123", "/downloads", "abb-automated")


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

    # Mock _get_strategy to return S1 (fails), then S2 (succeeds).
    strategy_fail = MagicMock()
    strategy_fail.remove_torrent.side_effect = Exception("Fail")

    strategy_ok = MagicMock()

    with patch.object(manager, "_get_strategy", side_effect=[strategy_fail, strategy_ok]) as mock_get_strat:
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            manager.remove_torrent("123")

            assert mock_get_strat.call_count == 2
            assert mock_logger.warning.called
            assert "Attempting to reconnect" in str(mock_logger.warning.call_args[0][0])
            strategy_fail.remove_torrent.assert_called_with("123")
            strategy_ok.remove_torrent.assert_called_with("123")


def test_add_magnet_retry_coverage(app: Flask, setup_manager: Any) -> None:
    """Test retry logic in add_magnet via mocked strategy."""
    manager = setup_manager(app)

    strategy_fail = MagicMock()
    strategy_fail.add_magnet.side_effect = Exception("Fail")

    strategy_ok = MagicMock()

    with patch.object(manager, "_get_strategy", side_effect=[strategy_fail, strategy_ok]) as mock_get_strat:
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            manager.add_magnet("magnet:...", "/save")

            assert mock_get_strat.call_count == 2
            assert mock_logger.warning.called
            assert "Attempting to reconnect" in str(mock_logger.warning.call_args[0][0])


def test_get_status_retry_coverage(app: Flask, setup_manager: Any) -> None:
    """Test retry logic in get_status."""
    manager = setup_manager(app)

    strategy_mock = MagicMock()
    mock_status = cast(list[TorrentStatus], [{"name": "test"}])
    strategy_mock.get_status.return_value = mock_status

    with patch.object(manager, "_get_strategy") as mock_get_strat:
        strategy_fail = MagicMock()
        strategy_fail.get_status.side_effect = Exception("Conn Error")

        mock_get_strat.side_effect = [strategy_fail, strategy_mock]

        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            status = manager.get_status()

            assert len(status) == 1
            assert status[0]["name"] == "test"
            assert mock_logger.warning.called
            assert "Reconnecting" in str(mock_logger.warning.call_args[0][0])


def test_force_disconnect_exception_handling(app: Flask, setup_manager: Any) -> None:
    """Test that exceptions during close() in _force_disconnect are caught and logged."""
    manager = setup_manager(app)

    mock_strategy = MagicMock()
    mock_strategy.close.side_effect = Exception("Close Error")
    manager._local.strategy = mock_strategy

    with patch("audiobook_automated.clients.manager.logger") as mock_logger:
        manager._force_disconnect()

        mock_logger.warning.assert_called()
        args, _ = mock_logger.warning.call_args
        assert "Error closing strategy during reconnect" in args[0]
        assert "Close Error" in str(args[0])

    assert manager._local.strategy is None


def test_verify_credentials_import_error(app: Flask, setup_manager: Any) -> None:
    """Test verify_credentials handles ImportError gracefully (e.g. missing plugin)."""
    manager = setup_manager(app, DL_CLIENT="qbittorrent")

    original_import = importlib.import_module

    def side_effect(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == ".qbittorrent" or name == "audiobook_automated.clients.qbittorrent":
            raise ImportError("Module missing")
        return original_import(name, *args, **kwargs)

    with patch("importlib.import_module", side_effect=side_effect):
        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            result = manager.verify_credentials()

            assert result is False
            # Verify the error was logged in _get_strategy (via "Could not load..." path)
            mock_logger.error.assert_called()
            assert "Could not load strategy for client" in mock_logger.error.call_args[0][0]


def test_load_strategy_class_none(app: Flask, setup_manager: Any) -> None:
    """Test that _load_strategy_class returns None if client_name is None.

    This covers the `if not client_name: return None` check in manager.py.
    """
    manager = setup_manager(app)
    assert manager._load_strategy_class(None) is None


def test_syntax_error_in_plugin(app: Flask) -> None:
    """Test that a SyntaxError in the plugin module is caught and logged."""
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "test_client"

    # We need to initialize the app so manager picks up the config
    manager.init_app(app)

    with patch("importlib.import_module") as mock_import:
        mock_import.side_effect = SyntaxError("Test Syntax Error")

        strategy = manager._get_strategy()

        assert strategy is None
        mock_import.assert_called()


def test_invalid_dl_client_regex(app: Flask) -> None:
    """Test that init_app raises RuntimeError for invalid DL_CLIENT characters."""
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "invalid-client-name"  # Hyphens not allowed

    with pytest.raises(RuntimeError) as excinfo:
        manager.init_app(app)

    assert "Invalid DL_CLIENT value" in str(excinfo.value)


def test_missing_dl_client(app: Flask) -> None:
    """Test that init_app handles missing DL_CLIENT gracefully (sets None)."""
    manager = TorrentManager()
    app.config["DL_CLIENT"] = None

    manager.init_app(app)
    assert manager.client_type is None


def test_import_error_dependency(app: Flask) -> None:
    """Test that ImportError for a dependency INSIDE the plugin raises the error."""
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "valid_client"
    manager.init_app(app)

    # We simulate:
    # 1. importlib.import_module("...valid_client") raises ImportError
    # 2. BUT the name of the missing module is NOT the client itself, but 'some_dependency'

    with patch("importlib.import_module") as mock_import:
        # Create an ImportError with a specific name attribute
        error = ModuleNotFoundError("No module named 'some_dependency'")
        error.name = "some_dependency"  # Crucial: NOT 'audiobook_automated.clients.valid_client'
        mock_import.side_effect = error

        with pytest.raises(ImportError) as excinfo:
            manager._load_strategy_class("valid_client")

        assert str(excinfo.value) == "No module named 'some_dependency'"


def test_load_strategy_missing_plugin_vs_dependency(app: Flask, setup_manager: Any) -> None:
    """Test that manager correctly distinguishes between missing plugin vs missing dependency."""
    manager = setup_manager(app)
    client_name = "missing_client"

    # CASE 1: The plugin itself is missing (should return None, log error, NO raise)
    with patch("importlib.import_module") as mock_import:
        # e.name matches the plugin full path
        error = ModuleNotFoundError(f"No module named '{client_name}'")
        error.name = f"audiobook_automated.clients.{client_name}"
        mock_import.side_effect = error

        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            result = manager._load_strategy_class(client_name, suppress_errors=False)
            assert result is None
            mock_logger.error.assert_called()
            assert f"Client plugin '{client_name}' not found" in mock_logger.error.call_args[0][0]

    # CASE 2: A dependency inside the plugin is missing (should RAISE ImportError)
    with patch("importlib.import_module") as mock_import:
        # e.name matches some random dependency
        error = ModuleNotFoundError("No module named 'some_lib'")
        error.name = "some_lib"
        mock_import.side_effect = error

        with pytest.raises(ModuleNotFoundError) as exc:
            manager._load_strategy_class(client_name)
        assert exc.value.name == "some_lib"
