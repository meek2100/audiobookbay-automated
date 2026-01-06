# File: tests/unit/clients/test_manager.py
"""Unit tests for TorrentManager."""

# pyright: reportPrivateUsage=false

import threading
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from audiobook_automated.clients.base import TorrentClientStrategy
from audiobook_automated.clients.manager import TorrentManager


def test_manager_init_app_invalid_client_name(app: Flask) -> None:
    """Test that init_app raises error for invalid client name."""
    app.config["DL_CLIENT"] = "invalid-name!"
    manager = TorrentManager()
    with pytest.raises(RuntimeError, match="Invalid DL_CLIENT value"):
        manager.init_app(app)


def test_init_app_missing_client(app: Flask) -> None:
    """Test init_app when DL_CLIENT is missing."""
    app.config.pop("DL_CLIENT", None)
    manager = TorrentManager()
    manager.init_app(app)
    assert manager.client_type is None


def test_load_strategy_missing_plugin() -> None:
    """Test that missing plugin module is handled based on suppress_errors."""
    manager = TorrentManager()

    # The manager constructs full_module_name as "audiobook_automated.clients.{client_name}"
    # We must match this name for the "plugin missing" path.
    name = "audiobook_automated.clients.ghost_client"

    # Patch logger FIRST to avoid triggering import_module mock during patch setup
    with patch("audiobook_automated.clients.manager.logger.error") as mock_error:
        with patch(
            "importlib.import_module",
            side_effect=ModuleNotFoundError(name=name, path="audiobook_automated/clients/ghost_client.py"),
        ):
            # Should return None and log error if suppress_errors=False
            strategy = manager._load_strategy_class("ghost_client", suppress_errors=False)
            assert strategy is None
            mock_error.assert_called_with("Client plugin 'ghost_client' not found.")

            # Test direct call with suppress=True
            strategy = manager._load_strategy_class("ghost_client", suppress_errors=True)
            assert strategy is None


def test_load_strategy_missing_dependency() -> None:
    """Test that missing dependency inside plugin raises ModuleNotFoundError."""
    manager = TorrentManager()
    error = ModuleNotFoundError(name="random_lib")

    with patch("importlib.import_module", side_effect=error):
        with pytest.raises(ModuleNotFoundError) as exc:
            manager._load_strategy_class("existing_client")
        assert exc.value.name == "random_lib"


def test_init_app_valid(app: Flask) -> None:
    """Test init_app with valid configuration."""
    app.config["DL_CLIENT"] = "test_client"
    app.config["DL_HOST"] = "localhost"
    app.config["DL_PORT"] = 1234
    app.config["CLIENT_TIMEOUT"] = 45

    manager = TorrentManager()

    # Mock _load_strategy_class to avoid actual import
    with patch.object(manager, "_load_strategy_class") as mock_load:
        mock_strategy_cls = MagicMock()
        mock_strategy_cls.DEFAULT_PORT = 9999
        mock_load.return_value = mock_strategy_cls

        manager.init_app(app)

        assert manager.client_type == "test_client"
        assert manager.port == 1234
        assert manager.client_timeout == 45
        # Should call speculative check
        mock_load.assert_called()


def test_init_app_url_parsing(app: Flask) -> None:
    """Test DL_URL parsing in init_app."""
    app.config["DL_CLIENT"] = "test"
    app.config["DL_URL"] = "https://remote:5678"

    manager = TorrentManager()

    with patch.object(manager, "_load_strategy_class"):
        manager.init_app(app)

        assert manager.host == "remote"
        assert manager.port == 5678
        assert manager.scheme == "https"


def test_get_strategy_success(app: Flask) -> None:
    """Test successful strategy retrieval and connection."""
    app.config["DL_CLIENT"] = "mock_client"
    app.config["CLIENT_TIMEOUT"] = 30
    manager = TorrentManager()
    manager.init_app(app)

    mock_strategy = MagicMock(spec=TorrentClientStrategy)

    with patch.object(manager, "_load_strategy_class", return_value=MagicMock(return_value=mock_strategy)):
        strategy = manager._get_strategy()

        assert strategy is mock_strategy
        mock_strategy.connect.assert_called_once()
        # Ensure it's cached in thread local
        assert manager._local.strategy is mock_strategy


def test_get_strategy_syntax_error(app: Flask) -> None:
    """Test handling of SyntaxError during strategy loading."""
    app.config["DL_CLIENT"] = "bad_client"
    manager = TorrentManager()
    manager.init_app(app)

    with patch.object(manager, "_load_strategy_class", side_effect=SyntaxError("Bad syntax")):
        strategy = manager._get_strategy()
        assert strategy is None


def test_verify_credentials_success(app: Flask) -> None:
    """Test verify_credentials returns True on success."""
    app.config["DL_CLIENT"] = "good"
    manager = TorrentManager()
    manager.init_app(app)

    with patch.object(manager, "_get_strategy", return_value=MagicMock()):
        assert manager.verify_credentials() is True


def test_verify_credentials_failure(app: Flask) -> None:
    """Test verify_credentials returns False on failure."""
    app.config["DL_CLIENT"] = "bad"
    manager = TorrentManager()
    manager.init_app(app)

    with patch.object(manager, "_get_strategy", return_value=None):
        assert manager.verify_credentials() is False


def test_add_magnet_retry_logic(app: Flask) -> None:
    """Test add_magnet retries on failure."""
    app.config["DL_CLIENT"] = "retry_client"
    manager = TorrentManager()
    manager.init_app(app)

    mock_strategy = MagicMock(spec=TorrentClientStrategy)
    # Fail first, succeed second
    mock_strategy.add_magnet.side_effect = [Exception("Fail"), None]

    with patch.object(manager, "_get_strategy", return_value=mock_strategy):
        with patch.object(manager, "_force_disconnect", wraps=manager._force_disconnect) as mock_disconnect:
            manager.add_magnet("magnet:...", "/path")

            assert mock_strategy.add_magnet.call_count == 2
            mock_disconnect.assert_called_once()


def test_thread_local_isolation() -> None:
    """Test that strategies are isolated between threads."""
    manager = TorrentManager()
    manager.client_type = "dummy"

    # Simulate strategy in main thread
    manager._local.strategy = MagicMock()
    main_strategy = manager._local.strategy

    def check_thread() -> None:
        # In new thread, strategy should be None
        assert manager._local.strategy is None
        manager._local.strategy = MagicMock()
        assert manager._local.strategy is not main_strategy

    t = threading.Thread(target=check_thread)
    t.start()
    t.join()


# --- New Tests for Full Coverage ---


def test_init_app_speculative_check_exception(app: Flask) -> None:
    """Test exception handling during init_app speculative load."""
    app.config["DL_CLIENT"] = "broken_client"
    manager = TorrentManager()

    with patch.object(manager, "_load_strategy_class", side_effect=Exception("Load error")):
        # Should swallow exception and log debug
        manager.init_app(app)
        # Verify defaults remain
        assert manager.port == 8080


def test_init_app_url_parsing_failure(app: Flask) -> None:
    """Test exception handling during DL_URL parsing."""
    app.config["DL_CLIENT"] = "test"
    app.config["DL_URL"] = "http://["  # Invalid URL
    app.config["DL_PORT"] = 9000

    manager = TorrentManager()

    with patch.object(manager, "_load_strategy_class"):
        manager.init_app(app)
        # Should fallback to raw config
        assert manager.port == 9000


def test_init_app_deluge_warning(app: Flask, caplog: pytest.LogCaptureFixture) -> None:
    """Test Deluge warning when DL_HOST is missing."""
    app.config["DL_CLIENT"] = "deluge"
    # Ensure DL_HOST is explicitly None
    app.config["DL_HOST"] = None

    manager = TorrentManager()
    with patch.object(manager, "_load_strategy_class"):
        manager.init_app(app)
        assert "Defaulting Deluge to localhost" in caplog.text


def test_load_strategy_empty_name() -> None:
    """Test _load_strategy_class returns None for empty name."""
    manager = TorrentManager()
    assert manager._load_strategy_class(None) is None


def test_load_strategy_import_error() -> None:
    """Test generic ImportError handling."""
    manager = TorrentManager()
    with patch("importlib.import_module", side_effect=ImportError("Generic import error")):
        assert manager._load_strategy_class("test_client") is None


def test_get_strategy_early_return() -> None:
    """Test _get_strategy returns cached instance."""
    manager = TorrentManager()
    manager.client_type = "cached"
    mock_strategy = MagicMock()
    manager._local.strategy = mock_strategy

    # Should return cached without calling load
    assert manager._get_strategy() is mock_strategy


def test_get_strategy_no_client() -> None:
    """Test _get_strategy returns None if client_type not set."""
    manager = TorrentManager()
    manager.client_type = None
    assert manager._get_strategy() is None


def test_get_strategy_generic_exception(app: Flask) -> None:
    """Test generic exception handling in _get_strategy."""
    app.config["DL_CLIENT"] = "error_client"
    manager = TorrentManager()
    manager.init_app(app)

    with patch.object(manager, "_load_strategy_class", side_effect=Exception("Generic")):
        assert manager._get_strategy() is None


def test_force_disconnect_exception() -> None:
    """Test exception swallowing in _force_disconnect."""
    manager = TorrentManager()
    mock_strategy = MagicMock()
    mock_strategy.close.side_effect = Exception("Close error")
    manager._local.strategy = mock_strategy

    manager._force_disconnect()
    assert manager._local.strategy is None


def test_remove_torrent_retry(app: Flask) -> None:
    """Test retry logic for remove_torrent."""
    app.config["DL_CLIENT"] = "retry_remove"
    manager = TorrentManager()
    manager.init_app(app)

    mock_strategy = MagicMock(spec=TorrentClientStrategy)
    mock_strategy.remove_torrent.side_effect = [Exception("Fail"), None]

    with patch.object(manager, "_get_strategy", return_value=mock_strategy):
        with patch.object(manager, "_force_disconnect", wraps=manager._force_disconnect) as mock_disconnect:
            manager.remove_torrent("hash123")
            assert mock_strategy.remove_torrent.call_count == 2
            mock_disconnect.assert_called_once()


def test_get_status_retry(app: Flask) -> None:
    """Test retry logic for get_status."""
    app.config["DL_CLIENT"] = "retry_status"
    manager = TorrentManager()
    manager.init_app(app)

    mock_strategy = MagicMock(spec=TorrentClientStrategy)
    mock_strategy.get_status.side_effect = [Exception("Fail"), []]

    with patch.object(manager, "_get_strategy", return_value=mock_strategy):
        with patch.object(manager, "_force_disconnect", wraps=manager._force_disconnect) as mock_disconnect:
            result = manager.get_status()
            assert result == []
            assert mock_strategy.get_status.call_count == 2
            mock_disconnect.assert_called_once()


def test_load_strategy_missing_plugin_log_error() -> None:
    """Test that missing plugin module logs error if suppress_errors=False."""
    manager = TorrentManager()
    manager.client_type = "ghost_client"

    # We need to construct the expected full module name to match logic in manager.py
    # package_name is usually "audiobook_automated.clients" when running tests against installed package
    # or just "audiobook_automated.clients" if imported.
    # The manager uses __package__ or "audiobook_automated.clients".

    full_module_name = "audiobook_automated.clients.ghost_client"
    error = ModuleNotFoundError(name=full_module_name, path="audiobook_automated/clients/ghost_client.py")

    # Patch logger FIRST to avoid triggering import_module mock during patch setup
    with patch("audiobook_automated.clients.manager.logger") as mock_logger:
        with patch("importlib.import_module", side_effect=error):
            strategy = manager._load_strategy_class("ghost_client", suppress_errors=False)
            assert strategy is None
            mock_logger.error.assert_called_with("Client plugin 'ghost_client' not found.")


def test_get_strategy_load_returns_none(app: Flask) -> None:
    """Test _get_strategy when loader returns None (e.g. valid name but logic failure)."""
    app.config["DL_CLIENT"] = "dummy"
    manager = TorrentManager()
    manager.init_app(app)

    with patch.object(manager, "_load_strategy_class", return_value=None):
        assert manager._get_strategy() is None


def test_add_magnet_not_connected(app: Flask) -> None:
    """Test add_magnet raises ConnectionError when not connected."""
    app.config["DL_CLIENT"] = "dummy"
    manager = TorrentManager()
    manager.init_app(app)

    with patch.object(manager, "_get_strategy", return_value=None):
        # We must expect ConnectionError to be raised eventually
        # logic: add_magnet -> _add_magnet_logic (raises) -> catch -> _force_disconnect -> _add_magnet_logic (raises) -> Propagates
        with pytest.raises(ConnectionError, match="Torrent client is not connected"):
            manager.add_magnet("magnet:...", "/path")


def test_remove_torrent_not_connected(app: Flask) -> None:
    """Test remove_torrent raises ConnectionError when not connected."""
    app.config["DL_CLIENT"] = "dummy"
    manager = TorrentManager()
    manager.init_app(app)

    with patch.object(manager, "_get_strategy", return_value=None):
        with pytest.raises(ConnectionError, match="Torrent client is not connected"):
            manager.remove_torrent("123")


def test_get_status_not_connected(app: Flask) -> None:
    """Test get_status raises ConnectionError when not connected."""
    app.config["DL_CLIENT"] = "dummy"
    manager = TorrentManager()
    manager.init_app(app)

    with patch.object(manager, "_get_strategy", return_value=None):
        with pytest.raises(ConnectionError, match="Torrent client is not connected"):
            manager.get_status()


def test_dl_client_import_error() -> None:
    """Test TorrentManager logs error on valid name but missing module."""
    from audiobook_automated.clients.manager import logger as manager_logger

    manager = TorrentManager()
    # Mock logger to verify error is logged
    with patch.object(manager_logger, "error") as mock_log:
        # Simulate ImportError during module load
        with patch("importlib.import_module", side_effect=ImportError("Import broken")):
            manager._load_strategy_class("valid_but_broken")
            mock_log.assert_called_with("Error importing client plugin 'valid_but_broken': Import broken")


def test_teardown_request() -> None:
    """Test teardown_request closes and clears the strategy."""
    manager = TorrentManager()
    mock_strategy = MagicMock()
    manager._local.strategy = mock_strategy

    manager.teardown_request(None)

    mock_strategy.close.assert_called_once()
    assert manager._local.strategy is None


def test_teardown_request_no_strategy() -> None:
    """Test teardown_request does nothing if no strategy exists."""
    manager = TorrentManager()
    manager._local.strategy = None

    # Should not raise
    manager.teardown_request(None)
    assert manager._local.strategy is None


def test_teardown_request_close_error() -> None:
    """Test teardown_request handles close exceptions gracefully."""
    manager = TorrentManager()
    mock_strategy = MagicMock()
    mock_strategy.close.side_effect = Exception("Close failure")
    manager._local.strategy = mock_strategy

    # Should log warning but not raise
    with patch("audiobook_automated.clients.manager.logger.warning") as mock_warn:
        manager.teardown_request(None)
        mock_warn.assert_called()
        assert "Error closing strategy" in mock_warn.call_args[0][0]

    # Strategy should still be cleared
    assert manager._local.strategy is None


def test_manager_syntax_error_handling(app: Flask) -> None:
    """Test that TorrentManager gracefully handles SyntaxError in plugins."""
    # Configure app to use a dummy client name
    app.config["DL_CLIENT"] = "broken_plugin"

    manager = TorrentManager()
    manager.init_app(app)

    # Patch import_module to raise SyntaxError when loading the plugin
    with patch("importlib.import_module", side_effect=SyntaxError("Invalid Syntax")):
        # Attempt to get strategy, which triggers the load
        strategy = manager._get_strategy()

        # Should return None and log the error (handled in implementation)
        assert strategy is None
        # We also want to verify it didn't crash
