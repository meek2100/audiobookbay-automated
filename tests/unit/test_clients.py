"""Unit tests for TorrentManager and Client Strategies."""

from typing import Any, Generator, cast
from unittest.mock import MagicMock, patch

import pytest

# --- FIX: Import Schema Classes ---
from deluge_web_client.schema import Response, TorrentOptions
from flask import Flask
from qbittorrentapi import LoginFailed

from audiobook_automated.clients import (
    DelugeStrategy,
    QbittorrentStrategy,
    TorrentManager,
    TorrentStatus,
    TransmissionStrategy,
)


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create a minimal Flask app for testing context."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    # Default configs that can be overridden by monkeypatch/direct assignment
    app.config["DL_CLIENT"] = "qbittorrent"
    app.config["DL_HOST"] = "localhost"
    app.config["DL_PORT"] = "8080"
    app.config["DL_USERNAME"] = "admin"
    app.config["DL_PASSWORD"] = "admin"
    app.config["DL_CATEGORY"] = "audiobooks"
    yield app


def setup_manager(app: Flask, **kwargs: Any) -> TorrentManager:
    """Helper to initialize TorrentManager with specific config overrides."""
    for k, v in kwargs.items():
        app.config[k] = v
    manager = TorrentManager()
    manager.init_app(app)
    return manager


# --- Manager Initialization & Configuration Tests ---


def test_init_with_dl_url(app: Flask) -> None:
    """Test that DL_URL takes precedence if provided directly."""
    manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://custom-url:1234", DL_HOST=None, DL_PORT=None)
    assert manager.dl_url == "http://custom-url:1234"


def test_init_dl_url_construction(app: Flask) -> None:
    """Test construction of DL_URL from host and port."""
    manager = setup_manager(app, DL_CLIENT="deluge", DL_URL=None, DL_HOST="myhost", DL_PORT="9999", DL_SCHEME="https")
    assert manager.dl_url == "https://myhost:9999"


def test_init_dl_url_deluge_default(app: Flask) -> None:
    """Test default DL_URL for Deluge when host/port missing."""
    with patch("audiobook_automated.clients.logger") as mock_logger:
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL=None, DL_HOST=None, DL_PORT=None)
        assert manager.dl_url == "http://localhost:8112"
        mock_logger.warning.assert_called_with("DL_HOST missing. Defaulting Deluge URL to localhost:8112.")


def test_init_dl_port_missing(app: Flask) -> None:
    """Test that default port is assigned if DL_HOST is present but DL_PORT is missing.

    Covers app/clients.py logic for default port assignment.
    """
    with patch("audiobook_automated.clients.logger") as mock_logger:
        # Case 1: Deluge -> 8112
        manager = setup_manager(app, DL_CLIENT="deluge", DL_HOST="deluge-host", DL_PORT=None)
        assert manager.port == 8112
        assert manager.dl_url == "http://deluge-host:8112"
        mock_logger.info.assert_called_with("DL_PORT missing. Defaulting to 8112 for deluge.")

        # Case 2: Other (qBittorrent) -> 8080
        manager_qb = setup_manager(app, DL_CLIENT="qbittorrent", DL_HOST="qb-host", DL_PORT=None)
        assert manager_qb.port == 8080
        assert manager_qb.dl_url == "http://qb-host:8080"


def test_init_dl_url_parse_failure(app: Flask) -> None:
    """Test that init_app handles URL parsing exceptions gracefully."""
    with (
        patch("audiobook_automated.clients.urlparse") as mock_parse,
        patch("audiobook_automated.clients.logger") as mock_logger,
    ):
        mock_parse.side_effect = ValueError("Parsing boom")
        setup_manager(app, DL_URL="http://malformed")
        mock_logger.warning.assert_called()
        args, _ = mock_logger.warning.call_args
        assert "Failed to parse DL_URL" in args[0]


def test_verify_credentials_success(app: Flask) -> None:
    """Targets verify_credentials success path (True)."""
    manager = setup_manager(app)
    # Mock _get_strategy to return a mock object (truthy)
    with patch.object(manager, "_get_strategy", return_value=MagicMock()):
        assert manager.verify_credentials() is True


def test_verify_credentials_failure(app: Flask) -> None:
    """Targets verify_credentials failure path (False)."""
    manager = setup_manager(app)
    # Mock _get_strategy to return None
    with patch.object(manager, "_get_strategy", return_value=None):
        assert manager.verify_credentials() is False


# --- Strategy Implementation Tests ---


def test_qbittorrent_strategy_add_magnet(app: Flask) -> None:
    """Test that QbittorrentStrategy adds magnet correctly."""
    with patch("audiobook_automated.clients.QbClient") as MockQbClient:
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


def test_qbittorrent_add_magnet_failure_response(app: Flask) -> None:
    """Test logging when qBittorrent returns a failure string."""
    with patch("audiobook_automated.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        mock_instance.torrents_add.return_value = "Fails."

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        with patch("audiobook_automated.clients.logger") as mock_logger:
            strategy.add_magnet("magnet:?xt=urn:btih:123", "/downloads/Book", "audiobooks")
            args, _ = mock_logger.warning.call_args
            assert "qBittorrent returned failure response" in args[0]
            assert "Fails." in args[0]


def test_add_magnet_invalid_path_logging(app: Flask) -> None:
    """Test logging when the Torrent Client returns an error related to an invalid save path."""
    with patch("audiobook_automated.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        # FIX: Return "Fails." to trigger the logging logic, as custom error messages aren't captured
        mock_instance.torrents_add.return_value = "Fails."

        manager = setup_manager(app)
        # Using manager to trigger strategy creation and delegation
        manager._get_strategy()

        with patch("audiobook_automated.clients.logger") as mock_logger:
            manager.add_magnet("magnet:?xt=urn:btih:123", "/root/protected")
            # Warning will come from strategy logging
            assert mock_logger.warning.called
            args, _ = mock_logger.warning.call_args
            assert "qBittorrent returned failure response" in args[0]


def test_remove_torrent_qbittorrent(app: Flask) -> None:
    """Test removing torrent for qBittorrent."""
    with patch("audiobook_automated.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value

        strategy = QbittorrentStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("hash123")

        mock_instance.torrents_delete.assert_called_with(torrent_hashes="hash123", delete_files=False)


# --- Transmission Strategy Tests ---


def test_transmission_add_magnet(app: Flask) -> None:
    """Test that TransmissionStrategy correctly calls the underlying client."""
    with patch("audiobook_automated.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:ABC", "/downloads/Book", "audiobooks")

        mock_instance.add_torrent.assert_called_with(
            "magnet:?xt=urn:btih:ABC", download_dir="/downloads/Book", labels=["audiobooks"]
        )


def test_transmission_add_magnet_fallback(app: Flask) -> None:
    """Test that transmission falls back to adding torrent without label if first attempt fails."""
    with patch("audiobook_automated.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        mock_instance.add_torrent.side_effect = [TypeError("unexpected keyword argument 'labels'"), None]

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        with patch("audiobook_automated.clients.logger") as mock_logger:
            strategy.add_magnet("magnet:?xt=urn:btih:FALLBACK", "/downloads/Book", "audiobooks")
            assert mock_logger.warning.called
            args, _ = mock_logger.warning.call_args
            assert "Transmission label assignment failed" in args[0]

        assert mock_instance.add_torrent.call_count == 2


def test_transmission_add_magnet_generic_exception_fallback(app: Flask) -> None:
    """Test that Transmission falls back even on generic exceptions."""
    with patch("audiobook_automated.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        mock_instance.add_torrent.side_effect = [Exception("Generic Protocol Error"), None]

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        with patch("audiobook_automated.clients.logger") as mock_logger:
            strategy.add_magnet("magnet:?xt=urn:btih:GENERIC", "/downloads/Book", "audiobooks")
            args, _ = mock_logger.warning.call_args
            assert "Transmission label assignment failed" in args[0]

        assert mock_instance.add_torrent.call_count == 2


def test_init_transmission_failure(app: Flask) -> None:
    """Test handling of Transmission connection failure."""
    with patch("audiobook_automated.clients.TxClient") as MockTx:
        MockTx.side_effect = Exception("Connection refused")
        manager = setup_manager(app, DL_CLIENT="transmission")
        assert manager._get_strategy() is None


def test_remove_torrent_transmission_hash(app: Flask) -> None:
    """Test removing torrent for Transmission using a string hash."""
    with patch("audiobook_automated.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("hash123")

        mock_instance.remove_torrent.assert_called_with(ids=["hash123"], delete_data=False)


def test_remove_torrent_transmission_numeric_id(app: Flask) -> None:
    """Test removing torrent for Transmission with a numeric ID."""
    with patch("audiobook_automated.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("12345")

        mock_instance.remove_torrent.assert_called_with(ids=[12345], delete_data=False)


def test_remove_torrent_transmission_int_conversion_failure(app: Flask) -> None:
    """Test removing torrent for Transmission when ID is not an integer."""
    with patch("audiobook_automated.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("not_an_int")

        mock_instance.remove_torrent.assert_called_with(ids=["not_an_int"], delete_data=False)


# --- Deluge Strategy Tests ---


def test_deluge_add_magnet(app: Flask) -> None:
    """Test DelugeStrategy add_magnet."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        # FIX: login must return success for connect to pass
        mock_instance.login.return_value = Response(result=True, error=None)
        # FIX: Mock get_plugins to return Label
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:XYZ", "/downloads/Book", "audiobooks")

        mock_instance.login.assert_called_once()

        # --- FIX: Assert called with TorrentOptions object ---
        expected_options = TorrentOptions(download_location="/downloads/Book", label="audiobooks")
        mock_instance.add_torrent_magnet.assert_called_with("magnet:?xt=urn:btih:XYZ", torrent_options=expected_options)


def test_init_deluge_failure(app: Flask) -> None:
    """Test handling of Deluge login exception in manager."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        # Case: Exception raised during login call
        MockDeluge.return_value.login.side_effect = Exception("Login failed")
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")

        with patch("audiobook_automated.clients.logger") as mock_logger:
            assert manager._get_strategy() is None
            mock_logger.error.assert_called()
            args, _ = mock_logger.error.call_args
            assert "Error initializing torrent client strategy" in args[0]


def test_init_deluge_auth_failure(app: Flask) -> None:
    """Test handling of Deluge login returning failure (False) result.

    This ensures the 'if not response.result:' check in clients.py is covered.
    """
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        # Case: Login returns Response(result=False)
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=False, error="Bad Password")

        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")

        with patch("audiobook_automated.clients.logger") as mock_logger:
            assert manager._get_strategy() is None
            mock_logger.error.assert_called()
            args, _ = mock_logger.error.call_args
            # Verify we caught the ConnectionError raised by our check
            assert "Failed to login to Deluge" in str(args[0])


def test_init_deluge_constructor_failure(app: Flask) -> None:
    """Test handling of DelugeWebClient constructor failure."""
    with patch("audiobook_automated.clients.DelugeWebClient", side_effect=Exception("Init Error")):
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        assert manager._get_strategy() is None


def test_remove_torrent_deluge(app: Flask) -> None:
    """Test removing torrent for Deluge."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        strategy.remove_torrent("hash123")

        mock_instance.remove_torrent.assert_called_with("hash123", remove_data=False)


def test_deluge_label_plugin_error(app: Flask) -> None:
    """Test that Deluge falls back to adding torrent without label if plugin is missing."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        # FIX: Enable plugin so we try adding with label first
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)

        mock_instance.add_torrent_magnet.side_effect = [
            Exception("Unknown parameter 'label'"),
            None,
        ]

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book", "audiobooks")

        assert mock_instance.add_torrent_magnet.call_count == 2

        # --- FIX: Verify calls with TorrentOptions ---
        # 1. First call has label
        expected_full = TorrentOptions(download_location="/downloads/Book", label="audiobooks")
        mock_instance.add_torrent_magnet.assert_any_call("magnet:?xt=urn:btih:FAIL", torrent_options=expected_full)

        # 2. Second call has NO label
        expected_fallback = TorrentOptions(download_location="/downloads/Book")
        mock_instance.add_torrent_magnet.assert_any_call("magnet:?xt=urn:btih:FAIL", torrent_options=expected_fallback)


def test_deluge_fallback_robustness_strings(app: Flask) -> None:
    """Test that the fallback works with various Deluge error messages."""
    error_variations = [
        "Unknown parameter 'label'",
        "Parameter 'label' not found",
        "Invalid argument: label",
    ]

    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        # FIX: Enable plugin
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)

        for error_msg in error_variations:
            mock_instance.add_torrent_magnet.reset_mock()
            mock_instance.add_torrent_magnet.side_effect = [
                Exception(error_msg),
                None,
            ]

            strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
            strategy.connect()
            strategy.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book", "audiobooks")

            assert mock_instance.add_torrent_magnet.call_count == 2


def test_deluge_fallback_failure(app: Flask) -> None:
    """Test that if the Deluge fallback also fails, it raises an error."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        # FIX: Enable plugin
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)

        mock_instance.add_torrent_magnet.side_effect = [
            Exception("Unknown parameter 'label'"),
            Exception("Critical Network Failure"),
        ]

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        with patch("audiobook_automated.clients.logger") as mock_logger:
            with pytest.raises(Exception) as exc:
                strategy.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book", "audiobooks")

            assert "Critical Network Failure" in str(exc.value)
            found = any("Deluge fallback failed" in str(call) for call in mock_logger.error.call_args_list)
            assert found


def test_deluge_add_magnet_generic_error(app: Flask) -> None:
    """Test that a generic error in Deluge addition is raised."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)
        mock_instance.add_torrent_magnet.side_effect = Exception("Generic Failure")

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        with pytest.raises(Exception) as exc:
            strategy.add_magnet("magnet:...", "/path", "cat")
        assert "Generic Failure" in str(exc.value)


def test_deluge_connect_plugin_check_failure(app: Flask) -> None:
    """Test handling of exception during Deluge plugin check."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        # Simulate exception during get_plugins
        mock_instance.get_plugins.side_effect = Exception("Plugin API Error")

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")

        with patch("audiobook_automated.clients.logger") as mock_logger:
            strategy.connect()

            assert strategy.label_plugin_enabled is False
            assert mock_logger.warning.called
            assert "Could not verify Deluge plugins" in str(mock_logger.warning.call_args[0])


def test_deluge_add_magnet_no_label_plugin(app: Flask) -> None:
    """Test add_magnet when label plugin is disabled/missing."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        # Plugins result without "Label"
        mock_instance.get_plugins.return_value = Response(result=["OtherPlugin"], error=None)

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        assert strategy.label_plugin_enabled is False

        strategy.add_magnet("magnet:?xt=urn:btih:NO_LABEL", "/downloads/Book", "audiobooks")

        # Verify called with options WITHOUT label
        expected_options = TorrentOptions(download_location="/downloads/Book")
        mock_instance.add_torrent_magnet.assert_called_with(
            "magnet:?xt=urn:btih:NO_LABEL", torrent_options=expected_options
        )


def test_deluge_add_magnet_failure_no_label(app: Flask) -> None:
    """Test exception propagation when add_magnet fails and plugins are disabled."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        # Plugins disabled/missing
        mock_instance.get_plugins.return_value = Response(result=[], error=None)

        mock_instance.add_torrent_magnet.side_effect = Exception("Some Error")

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        assert strategy.label_plugin_enabled is False

        with pytest.raises(Exception) as exc:
            strategy.add_magnet("magnet:...", "/path", "cat")

        assert "Some Error" in str(exc.value)


# --- Manager Connectivity & Error Handling Tests ---


def test_unsupported_client_strategy(app: Flask) -> None:
    """Test that unsupported clients return None and log error instead of crashing."""
    manager = setup_manager(app, DL_CLIENT="fake_client")

    with patch("audiobook_automated.clients.logger") as mock_logger:
        strategy = manager._get_strategy()
        assert strategy is None
        assert mock_logger.error.called
        args, _ = mock_logger.error.call_args
        assert "Error initializing torrent client strategy" in args[0]


def test_init_qbittorrent_login_failed(app: Flask) -> None:
    """Test handling of qBittorrent authentication failure."""
    with patch("audiobook_automated.clients.QbClient") as MockQb:
        MockQb.return_value.auth_log_in.side_effect = LoginFailed("Bad Auth")
        manager = setup_manager(app, DL_CLIENT="qbittorrent")
        assert manager._get_strategy() is None


def test_verify_credentials_fail(app: Flask) -> None:
    """Test verify_credentials returns False when client fails to init."""
    manager = setup_manager(app, DL_CLIENT="qbittorrent")
    with patch("audiobook_automated.clients.TorrentManager._get_strategy", return_value=None):
        assert manager.verify_credentials() is False


def test_remove_torrent_no_client_raises(app: Flask) -> None:
    """Test that an error is raised if no client can be connected during removal."""
    manager = setup_manager(app)
    with patch.object(manager, "_get_strategy", return_value=None):
        with pytest.raises(ConnectionError) as exc:
            manager.remove_torrent("123")
        assert "Torrent client is not connected" in str(exc.value)


def test_remove_torrent_retry(app: Flask) -> None:
    """Test that remove_torrent attempts to reconnect if the first call fails."""
    with patch("audiobook_automated.clients.QbClient"):
        manager = setup_manager(app)
        with patch.object(manager, "_remove_torrent_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), None]
            manager.remove_torrent("hash123")
            assert mock_logic.call_count == 2
            # THREAD SAFETY UPDATE: Checked threaded local instead of _client
            assert getattr(manager._local, "strategy", None) is None


def test_add_magnet_reconnect_retry(app: Flask) -> None:
    """Test that add_magnet attempts to reconnect if the first call fails."""
    with patch("audiobook_automated.clients.QbClient"):
        manager = setup_manager(app)
        # Patch the logic method to throw then succeed
        with patch.object(manager, "_add_magnet_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), None]
            manager.add_magnet("magnet:...", "/save")
            assert mock_logic.call_count == 2
            # THREAD SAFETY UPDATE: Checked threaded local instead of _client
            assert getattr(manager._local, "strategy", None) is None


def test_logic_methods_no_client(app: Flask) -> None:
    """Test that logic methods raise ConnectionError when strategy is None."""
    manager = setup_manager(app)
    # Force client to be None despite any init attempts
    with patch.object(manager, "_get_strategy", return_value=None):
        with pytest.raises(ConnectionError):
            manager._add_magnet_logic("magnet:...", "/path")

        with pytest.raises(ConnectionError):
            manager._get_status_logic()


# --- Utility Tests ---


def test_format_size_logic() -> None:
    """Verify that bytes are converted to human-readable strings correctly."""
    from audiobook_automated.clients import TorrentClientStrategy

    # Standard units
    assert TorrentClientStrategy._format_size(500) == "500.00 B"
    assert TorrentClientStrategy._format_size(1024) == "1.00 KB"
    assert TorrentClientStrategy._format_size(1048576) == "1.00 MB"
    assert TorrentClientStrategy._format_size(1073741824) == "1.00 GB"

    # Petabytes (Edge case)
    huge_number = 1024 * 1024 * 1024 * 1024 * 1024 * 5
    assert "5.00 PB" in TorrentClientStrategy._format_size(huge_number)

    # Invalid inputs
    assert TorrentClientStrategy._format_size(None) == "Unknown"
    assert TorrentClientStrategy._format_size("not a number") == "Unknown"

    bad_input: Any = [1, 2]
    assert TorrentClientStrategy._format_size(bad_input) == "Unknown"


# --- Status & Info Tests ---


def test_get_status_qbittorrent(app: Flask) -> None:
    """Test fetching status from qBittorrent."""
    with patch("audiobook_automated.clients.QbClient") as MockQbClient:
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


def test_get_status_qbittorrent_robustness(app: Flask) -> None:
    """Test qBittorrent handling of None progress."""
    with patch("audiobook_automated.clients.QbClient") as MockQbClient:
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


def test_get_status_transmission(app: Flask) -> None:
    """Test fetching status from Transmission."""
    with patch("audiobook_automated.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        mock_torrent = MagicMock()
        mock_torrent.id = 1
        mock_torrent.name = "Test Book"
        mock_torrent.progress = 75.0
        # FIX: Mock status as an object with a 'name' attribute
        mock_status = MagicMock()
        mock_status.name = "downloading"
        mock_torrent.status = mock_status
        mock_torrent.total_size = 1024
        # FIX: Ensure labels match
        mock_torrent.labels = ["cat"]

        mock_instance.get_torrents.return_value = [mock_torrent]

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0]["progress"] == 75.0
        assert results[0]["size"] == "1.00 KB"


def test_get_status_transmission_robustness(app: Flask) -> None:
    """Test fetching status from Transmission handles None values gracefully."""
    with patch("audiobook_automated.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        mock_torrent_bad = MagicMock()
        mock_torrent_bad.id = 2
        mock_torrent_bad.name = "Bad Torrent"
        mock_torrent_bad.progress = None
        mock_torrent_bad.total_size = None
        # FIX: Mock status as an object with a 'name' attribute
        mock_status_bad = MagicMock()
        mock_status_bad.name = "error"
        mock_torrent_bad.status = mock_status_bad
        # FIX: Ensure labels match
        mock_torrent_bad.labels = ["cat"]

        mock_instance.get_torrents.return_value = [mock_torrent_bad]

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0]["name"] == "Bad Torrent"
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "Unknown"


def test_get_status_deluge(app: Flask) -> None:
    """Test fetching status from Deluge."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        mock_response = MagicMock()
        mock_response.result = {"hash123": {"name": "D Book", "state": "Dl", "progress": 45.5, "total_size": 100}}
        mock_instance.get_torrents_status.return_value = mock_response

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0]["name"] == "D Book"


def test_get_status_deluge_empty_result(app: Flask) -> None:
    """Test handling of Deluge returning a None result payload."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        mock_response = MagicMock()
        mock_response.result = None
        mock_instance.get_torrents_status.return_value = mock_response

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        with patch("audiobook_automated.clients.logger") as mock_logger:
            results = strategy.get_status("cat")

        assert results == []
        args, _ = mock_logger.warning.call_args
        assert "Deluge returned empty or invalid" in args[0]


def test_get_status_deluge_unexpected_data_type(app: Flask) -> None:
    """Test handling of Deluge returning a result that is not a dict."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        mock_response = MagicMock()
        mock_response.result = ["unexpected", "list"]
        mock_instance.get_torrents_status.return_value = mock_response

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        with patch("audiobook_automated.clients.logger") as mock_logger:
            results = strategy.get_status("cat")

        assert results == []
        args, _ = mock_logger.warning.call_args
        assert "Deluge returned unexpected data type" in args[0]
        assert "list" in args[0]


def test_get_status_deluge_invalid_item_type(app: Flask) -> None:
    """
    Test Deluge handling of non-dict items in the response dict.
    Covers app/clients.py lines 356-357 (continue on invalid type).
    """
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        mock_response = MagicMock()
        # Mix valid and invalid entries
        mock_response.result = {
            "valid_hash": {"name": "Good Book", "state": "Dl", "progress": 100, "total_size": 1024},
            "bad_hash": "I am a string, not a dict",  # This triggers the check
        }
        mock_instance.get_torrents_status.return_value = mock_response

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        results = strategy.get_status("cat")

        # Should skip the bad one and process the good one
        assert len(results) == 1
        assert results[0]["name"] == "Good Book"


def test_get_status_deluge_robustness(app: Flask) -> None:
    """Test Deluge handling of None in individual torrent fields."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        mock_response = MagicMock()
        mock_response.result = {
            "hash999": {"name": "Broken Book", "state": "Error", "progress": None, "total_size": None}
        }
        mock_instance.get_torrents_status.return_value = mock_response

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0]["name"] == "Broken Book"
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "Unknown"


def test_get_status_deluge_malformed_data(app: Flask) -> None:
    """Test Deluge handling of malformed progress data."""
    with patch("audiobook_automated.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        mock_response = MagicMock()
        mock_response.result = {
            "hash_err": {"name": "Bad Data", "state": "Error", "progress": "Error", "total_size": 100}
        }
        mock_instance.get_torrents_status.return_value = mock_response

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0]["name"] == "Bad Data"
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "100.00 B"


def test_get_status_reconnect(app: Flask) -> None:
    """Test that get_status attempts to reconnect if the first call fails."""
    with patch("audiobook_automated.clients.QbClient"):
        manager = setup_manager(app)
        with patch.object(manager, "_get_status_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), []]
            result = manager.get_status()
            assert mock_logic.call_count == 2
            assert result == []
            # THREAD SAFETY UPDATE: Checked threaded local instead of _client
            assert getattr(manager._local, "strategy", None) is None


# --- Strategy Specific Safety Checks (Defensive coding coverage) ---


def test_strategy_not_connected_error_handling() -> None:
    """Ensure strategies raise ConnectionError if their client is None."""

    # 1. qBittorrent
    qb = QbittorrentStrategy("host", 80, "u", "p")
    # Don't call connect()
    with pytest.raises(ConnectionError, match="qBittorrent client not connected"):
        qb.add_magnet("m", "p", "c")
    with pytest.raises(ConnectionError, match="qBittorrent client not connected"):
        qb.remove_torrent("123")
    with pytest.raises(ConnectionError, match="qBittorrent client not connected"):
        qb.get_status("c")

    # 2. Transmission
    tx = TransmissionStrategy("host", 80, "u", "p")
    with pytest.raises(ConnectionError, match="Transmission client not connected"):
        tx.add_magnet("m", "p", "c")
    with pytest.raises(ConnectionError, match="Transmission client not connected"):
        tx.remove_torrent("123")
    with pytest.raises(ConnectionError, match="Transmission client not connected"):
        tx.get_status("c")

    # 3. Deluge
    dg = DelugeStrategy(None, "host", 80, "u", "p")
    with pytest.raises(ConnectionError, match="Deluge client not connected"):
        dg.add_magnet("m", "p", "c")
    with pytest.raises(ConnectionError, match="Deluge client not connected"):
        dg.remove_torrent("123")
    with pytest.raises(ConnectionError, match="Deluge client not connected"):
        dg.get_status("c")


# --- Coverage Fixes ---


def test_get_strategy_unsupported_coverage(app: Flask) -> None:
    """Test unsupported client raises ValueError internally."""
    manager = TorrentManager()
    manager.init_app(app)
    manager.client_type = "invalid_thing"

    with patch("audiobook_automated.clients.logger") as mock_logger:
        strategy = manager._get_strategy()
        assert strategy is None
        # Assert that the error log contains the message from ValueError
        assert mock_logger.error.called
        args, _ = mock_logger.error.call_args
        assert "Unsupported download client configured: invalid_thing" in str(args[0])


def test_remove_torrent_retry_coverage(app: Flask) -> None:
    """Test retry logic in remove_torrent."""
    manager = TorrentManager()
    manager.init_app(app)

    # Mock _get_strategy to fail first time (return None -> raises ConnectionError)
    # then succeed (return mock strategy)
    strategy_mock = MagicMock()

    with patch.object(manager, "_get_strategy") as mock_get_strat:
        mock_get_strat.side_effect = [None, strategy_mock]

        with patch("audiobook_automated.clients.logger") as mock_logger:
            manager.remove_torrent("123")

            # Verify retry log
            assert mock_logger.warning.called
            assert "Attempting to reconnect" in str(mock_logger.warning.call_args[0][0])

            # Verify _get_strategy called twice
            assert mock_get_strat.call_count == 2

            strategy_mock.remove_torrent.assert_called_with("123")


def test_get_status_retry_coverage(app: Flask) -> None:
    """Test retry logic in get_status."""
    manager = TorrentManager()
    manager.init_app(app)

    strategy_mock = MagicMock()
    # Return a dict that matches TorrentStatus structure partially or cast it
    mock_status = cast(list[TorrentStatus], [{"name": "test"}])
    strategy_mock.get_status.return_value = mock_status

    with patch.object(manager, "_get_strategy") as mock_get_strat:
        mock_get_strat.side_effect = [None, strategy_mock]

        with patch("audiobook_automated.clients.logger") as mock_logger:
            status = manager.get_status()

            assert len(status) == 1
            assert status[0]["name"] == "test"

            # Verify retry log
            assert mock_logger.warning.called
            assert "Reconnecting" in str(mock_logger.warning.call_args[0][0])

            assert mock_get_strat.call_count == 2
