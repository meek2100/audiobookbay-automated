"""Unit tests for TorrentManager wrapper."""

from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from qbittorrentapi import LoginFailed

from app.clients import TorrentManager


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


# --- Initialization & Connection Tests ---


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
    with patch("app.clients.logger") as mock_logger:
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL=None, DL_HOST=None, DL_PORT=None)
        assert manager.dl_url == "http://localhost:8112"
        mock_logger.warning.assert_called_with("DL_HOST missing. Defaulting Deluge URL to localhost:8112.")


def test_init_dl_port_missing(app: Flask) -> None:
    """Test that default port is assigned if DL_HOST is present but DL_PORT is missing.

    Covers app/clients.py logic for default port assignment.
    """
    with patch("app.clients.logger") as mock_logger:
        # Case 1: Deluge -> 8112
        manager = setup_manager(app, DL_CLIENT="deluge", DL_HOST="deluge-host", DL_PORT=None)
        assert manager.port == "8112"
        assert manager.dl_url == "http://deluge-host:8112"
        mock_logger.info.assert_called_with("DL_PORT missing. Defaulting to 8112 for deluge.")

        # Case 2: Other (qBittorrent) -> 8080
        manager_qb = setup_manager(app, DL_CLIENT="qbittorrent", DL_HOST="qb-host", DL_PORT=None)
        assert manager_qb.port == "8080"
        assert manager_qb.dl_url == "http://qb-host:8080"


def test_init_dl_url_parse_failure(app: Flask) -> None:
    """Test that init_app handles URL parsing exceptions gracefully.

    Covers the 'except Exception' block in init_app when parsing DL_URL.
    """
    with patch("app.clients.urlparse") as mock_parse, patch("app.clients.logger") as mock_logger:
        mock_parse.side_effect = ValueError("Parsing boom")

        # This triggers init_app
        setup_manager(app, DL_URL="http://malformed")

        mock_logger.warning.assert_called()
        args, _ = mock_logger.warning.call_args
        assert "Failed to parse DL_URL" in args[0]


def test_init_deluge_success(app: Flask) -> None:
    """Test successful Deluge initialization."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112", DL_PASSWORD="pass")

        # Explicitly call _get_client to trigger the initialization logic
        client = manager._get_client()

        assert client is not None
        # THREAD SAFETY UPDATE: Check thread-local storage instead of _client
        assert manager._local.client == mock_instance
        mock_instance.login.assert_called_once()


def test_verify_credentials_success(app: Flask) -> None:
    """Targets verify_credentials success path (True)."""
    manager = setup_manager(app)
    with patch.object(manager, "_get_client", return_value=MagicMock()):
        assert manager.verify_credentials() is True


def test_verify_credentials_failure(app: Flask) -> None:
    """Targets verify_credentials failure path (False)."""
    manager = setup_manager(app)
    with patch.object(manager, "_get_client", return_value=None):
        assert manager.verify_credentials() is False


def test_qbittorrent_add_magnet(app: Flask) -> None:
    with patch("app.clients.QbClient") as MockQbClient:
        # Setup the mock client instance
        mock_instance = MockQbClient.return_value
        mock_instance.torrents_add.return_value = "Ok."

        manager = setup_manager(app)
        # Ensure client is loaded
        manager._get_client()

        manager.add_magnet("magnet:?xt=urn:btih:123", "/downloads/Book")

        MockQbClient.assert_called_with(
            host="localhost",
            port=8080,
            username="admin",
            password="admin",
            REQUESTS_ARGS={"timeout": 30},  # UPDATED: Now requires explicit timeout
        )
        mock_instance.auth_log_in.assert_called_once()
        mock_instance.torrents_add.assert_called_with(
            urls="magnet:?xt=urn:btih:123", save_path="/downloads/Book", category="audiobooks"
        )


def test_qbittorrent_add_magnet_failure_response(app: Flask) -> None:
    """Test logging when qBittorrent returns a failure string."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        mock_instance.torrents_add.return_value = "Fails."

        manager = setup_manager(app)
        manager._get_client()

        with patch("app.clients.logger") as mock_logger:
            manager.add_magnet("magnet:?xt=urn:btih:123", "/downloads/Book")
            args, _ = mock_logger.warning.call_args
            assert "qBittorrent add returned unexpected response" in args[0]
            assert "Fails." in args[0]


def test_add_magnet_invalid_path_logging(app: Flask) -> None:
    """Test logging when the Torrent Client returns an error related to an invalid save path."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        mock_instance.torrents_add.return_value = "Invalid Save Path"

        manager = setup_manager(app)
        manager._get_client()

        with patch("app.clients.logger") as mock_logger:
            manager.add_magnet("magnet:?xt=urn:btih:123", "/root/protected")
            assert mock_logger.warning.called
            args, _ = mock_logger.warning.call_args
            assert "Invalid Save Path" in args[0]


def test_transmission_add_magnet(app: Flask) -> None:
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        manager = setup_manager(app, DL_CLIENT="transmission")
        manager.add_magnet("magnet:?xt=urn:btih:ABC", "/downloads/Book")

        mock_instance.add_torrent.assert_called_with(
            "magnet:?xt=urn:btih:ABC", download_dir="/downloads/Book", labels=["audiobooks"]
        )


def test_transmission_add_magnet_fallback(app: Flask) -> None:
    """Test that transmission falls back to adding torrent without label if first attempt fails."""
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        mock_instance.add_torrent.side_effect = [TypeError("unexpected keyword argument 'labels'"), None]

        manager = setup_manager(app, DL_CLIENT="transmission")

        with patch("app.clients.logger") as mock_logger:
            manager.add_magnet("magnet:?xt=urn:btih:FALLBACK", "/downloads/Book")
            assert mock_logger.warning.called
            args, _ = mock_logger.warning.call_args
            assert "Transmission label assignment failed" in args[0]

        assert mock_instance.add_torrent.call_count == 2


def test_transmission_add_magnet_generic_exception_fallback(app: Flask) -> None:
    """Test that Transmission falls back even on generic exceptions."""
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        mock_instance.add_torrent.side_effect = [Exception("Generic Protocol Error"), None]

        manager = setup_manager(app, DL_CLIENT="transmission")

        with patch("app.clients.logger") as mock_logger:
            manager.add_magnet("magnet:?xt=urn:btih:GENERIC", "/downloads/Book")
            args, _ = mock_logger.warning.call_args
            assert "Transmission label assignment failed" in args[0]

        assert mock_instance.add_torrent.call_count == 2


def test_deluge_add_magnet(app: Flask) -> None:
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        manager.add_magnet("magnet:?xt=urn:btih:XYZ", "/downloads/Book")

        mock_instance.login.assert_called_once()
        mock_instance.add_torrent_magnet.assert_called_with(
            "magnet:?xt=urn:btih:XYZ", save_directory="/downloads/Book", label="audiobooks"
        )


def test_unsupported_client(app: Flask) -> None:
    """Test that unsupported clients return None and log error instead of crashing."""
    manager = setup_manager(app, DL_CLIENT="fake_client")

    with patch("app.clients.logger") as mock_logger:
        client = manager._get_client()
        assert client is None
        assert mock_logger.error.called
        args, _ = mock_logger.error.call_args
        assert "Error initializing torrent client" in args[0]


def test_init_transmission_failure(app: Flask) -> None:
    """Test handling of Transmission connection failure."""
    with patch("app.clients.TxClient") as MockTx:
        MockTx.side_effect = Exception("Connection refused")
        manager = setup_manager(app, DL_CLIENT="transmission")
        assert manager._get_client() is None


def test_init_deluge_failure(app: Flask) -> None:
    """Test handling of Deluge login failure."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        MockDeluge.return_value.login.side_effect = Exception("Login failed")
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")

        with patch("app.clients.logger") as mock_logger:
            assert manager._get_client() is None
            mock_logger.error.assert_called()
            args, _ = mock_logger.error.call_args
            assert "Error initializing torrent client" in args[0]


def test_init_deluge_constructor_failure(app: Flask) -> None:
    """Test handling of DelugeWebClient constructor failure."""
    with patch("app.clients.DelugeWebClient", side_effect=Exception("Init Error")):
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        assert manager._get_client() is None


def test_init_qbittorrent_login_failed(app: Flask) -> None:
    """Test handling of qBittorrent authentication failure."""
    with patch("app.clients.QbClient") as MockQb:
        MockQb.return_value.auth_log_in.side_effect = LoginFailed("Bad Auth")
        manager = setup_manager(app, DL_CLIENT="qbittorrent")
        assert manager._get_client() is None


def test_verify_credentials_fail(app: Flask) -> None:
    """Test verify_credentials returns False when client fails to init."""
    manager = setup_manager(app, DL_CLIENT="qbittorrent")
    with patch("app.clients.TorrentManager._get_client", return_value=None):
        assert manager.verify_credentials() is False


# --- Utility Tests ---


def test_format_size_logic() -> None:
    """Verify that bytes are converted to human-readable strings correctly."""
    tm = TorrentManager
    # Standard units
    assert tm._format_size(500) == "500.00 B"
    assert tm._format_size(1024) == "1.00 KB"
    assert tm._format_size(1048576) == "1.00 MB"
    assert tm._format_size(1073741824) == "1.00 GB"

    # Petabytes (Edge case)
    huge_number = 1024 * 1024 * 1024 * 1024 * 1024 * 5
    assert "5.00 PB" in tm._format_size(huge_number)

    # Invalid inputs
    assert tm._format_size(None) == "Unknown"
    assert tm._format_size("not a number") == "Unknown"

    bad_input: Any = [1, 2]
    assert tm._format_size(bad_input) == "Unknown"


# --- Removal Tests ---


def test_remove_torrent_qbittorrent(app: Flask) -> None:
    """Test removing torrent for qBittorrent."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        manager = setup_manager(app)
        manager.remove_torrent("hash123")
        mock_instance.torrents_delete.assert_called_with(torrent_hashes="hash123", delete_files=False)


def test_remove_torrent_transmission_hash(app: Flask) -> None:
    """Test removing torrent for Transmission using a string hash."""
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        manager = setup_manager(app, DL_CLIENT="transmission")

        manager.remove_torrent("hash123")
        mock_instance.remove_torrent.assert_called_with(ids=["hash123"], delete_data=False)


def test_remove_torrent_transmission_numeric_id(app: Flask) -> None:
    """Test removing torrent for Transmission with a numeric ID."""
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        manager = setup_manager(app, DL_CLIENT="transmission")

        manager.remove_torrent("12345")
        mock_instance.remove_torrent.assert_called_with(ids=[12345], delete_data=False)


def test_remove_torrent_transmission_int_conversion_failure(app: Flask) -> None:
    """Test removing torrent for Transmission when ID is not an integer."""
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        manager = setup_manager(app, DL_CLIENT="transmission")

        manager.remove_torrent("not_an_int")
        mock_instance.remove_torrent.assert_called_with(ids=["not_an_int"], delete_data=False)


def test_remove_torrent_deluge(app: Flask) -> None:
    """Test removing torrent for Deluge."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")

        manager.remove_torrent("hash123")
        mock_instance.remove_torrent.assert_called_with("hash123", remove_data=False)


def test_remove_torrent_no_client_raises(app: Flask) -> None:
    """Test that an error is raised if no client can be connected during removal."""
    manager = setup_manager(app)
    with patch.object(manager, "_get_client", return_value=None):
        with pytest.raises(ConnectionError) as exc:
            manager.remove_torrent("123")
        assert "Torrent client is not connected" in str(exc.value)


def test_remove_torrent_retry(app: Flask) -> None:
    """Test that remove_torrent attempts to reconnect if the first call fails."""
    with patch("app.clients.QbClient"):
        manager = setup_manager(app)
        with patch.object(manager, "_remove_torrent_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), None]
            manager.remove_torrent("hash123")
            assert mock_logic.call_count == 2
            # THREAD SAFETY UPDATE: Checked threaded local instead of _client
            assert getattr(manager._local, "client", None) is None


# --- Status & Info Tests ---


def test_get_status_qbittorrent(app: Flask) -> None:
    """Test fetching status from qBittorrent."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value

        mock_torrent = MagicMock()
        mock_torrent.hash = "hash1"
        mock_torrent.name = "Test Book"
        mock_torrent.progress = 0.5
        mock_torrent.state = "downloading"
        mock_torrent.total_size = 1048576  # 1 MB

        mock_instance.torrents_info.return_value = [mock_torrent]

        manager = setup_manager(app)
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["name"] == "Test Book"
        assert results[0]["progress"] == 50.0
        assert results[0]["size"] == "1.00 MB"


def test_get_status_qbittorrent_robustness(app: Flask) -> None:
    """Test qBittorrent handling of None progress."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value

        mock_torrent = MagicMock()
        mock_torrent.hash = "hash_bad"
        mock_torrent.name = "Stalled Book"
        mock_torrent.progress = None
        mock_torrent.state = "metaDL"
        mock_torrent.total_size = None

        mock_instance.torrents_info.return_value = [mock_torrent]

        manager = setup_manager(app)
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "Unknown"


def test_get_status_transmission(app: Flask) -> None:
    """Test fetching status from Transmission."""
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        mock_torrent = MagicMock()
        mock_torrent.id = 1
        mock_torrent.name = "Test Book"
        mock_torrent.progress = 0.75
        # FIX: Mock status as an object with a 'name' attribute
        mock_status = MagicMock()
        mock_status.name = "downloading"
        mock_torrent.status = mock_status
        mock_torrent.total_size = 1024

        mock_instance.get_torrents.return_value = [mock_torrent]

        manager = setup_manager(app, DL_CLIENT="transmission")
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["progress"] == 75.0
        assert results[0]["size"] == "1.00 KB"


def test_get_status_transmission_robustness(app: Flask) -> None:
    """Test fetching status from Transmission handles None values gracefully."""
    with patch("app.clients.TxClient") as MockTxClient:
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

        mock_instance.get_torrents.return_value = [mock_torrent_bad]

        manager = setup_manager(app, DL_CLIENT="transmission")
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["name"] == "Bad Torrent"
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "Unknown"


def test_get_status_deluge(app: Flask) -> None:
    """Test fetching status from Deluge."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        mock_response.result = {"hash123": {"name": "D Book", "state": "Dl", "progress": 45.5, "total_size": 100}}
        mock_instance.get_torrents_status.return_value = mock_response
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        results = manager.get_status()
        assert len(results) == 1
        assert results[0]["name"] == "D Book"


def test_get_status_deluge_empty_result(app: Flask) -> None:
    """Test handling of Deluge returning a None result payload."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        mock_response.result = None
        mock_instance.get_torrents_status.return_value = mock_response

        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        with patch("app.clients.logger") as mock_logger:
            results = manager.get_status()

        assert results == []
        args, _ = mock_logger.warning.call_args
        assert "Deluge returned empty or invalid" in args[0]


def test_get_status_deluge_unexpected_data_type(app: Flask) -> None:
    """Test handling of Deluge returning a result that is not a dict."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        mock_response.result = ["unexpected", "list"]
        mock_instance.get_torrents_status.return_value = mock_response

        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")

        with patch("app.clients.logger") as mock_logger:
            results = manager.get_status()

        assert results == []
        args, _ = mock_logger.warning.call_args
        assert "Deluge returned unexpected data type" in args[0]
        assert "list" in args[0]


def test_get_status_deluge_invalid_item_type(app: Flask) -> None:
    """
    Test Deluge handling of non-dict items in the response dict.
    Covers app/clients.py lines 356-357 (continue on invalid type).
    """
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        # Mix valid and invalid entries
        mock_response.result = {
            "valid_hash": {"name": "Good Book", "state": "Dl", "progress": 100, "total_size": 1024},
            "bad_hash": "I am a string, not a dict",  # This triggers the check
        }
        mock_instance.get_torrents_status.return_value = mock_response

        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        results = manager.get_status()

        # Should skip the bad one and process the good one
        assert len(results) == 1
        assert results[0]["name"] == "Good Book"


def test_get_status_deluge_robustness(app: Flask) -> None:
    """Test Deluge handling of None in individual torrent fields."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        mock_response.result = {
            "hash999": {"name": "Broken Book", "state": "Error", "progress": None, "total_size": None}
        }
        mock_instance.get_torrents_status.return_value = mock_response

        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["name"] == "Broken Book"
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "Unknown"


def test_get_status_deluge_malformed_data(app: Flask) -> None:
    """Test Deluge handling of malformed progress data."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        mock_response.result = {
            "hash_err": {"name": "Bad Data", "state": "Error", "progress": "Error", "total_size": 100}
        }
        mock_instance.get_torrents_status.return_value = mock_response

        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["name"] == "Bad Data"
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "100.00 B"


def test_get_status_reconnect(app: Flask) -> None:
    """Test that get_status attempts to reconnect if the first call fails."""
    with patch("app.clients.QbClient"):
        manager = setup_manager(app)
        with patch.object(manager, "_get_status_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), []]
            result = manager.get_status()
            assert mock_logic.call_count == 2
            assert result == []
            # THREAD SAFETY UPDATE: Checked threaded local instead of _client
            assert getattr(manager._local, "client", None) is None


# --- Error Handling & Retries ---


def test_deluge_label_plugin_error(app: Flask) -> None:
    """Test that Deluge falls back to adding torrent without label if plugin is missing."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.add_torrent_magnet.side_effect = [
            Exception("Unknown parameter 'label'"),
            None,
        ]

        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        manager.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book")

        assert mock_instance.add_torrent_magnet.call_count == 2
        mock_instance.add_torrent_magnet.assert_any_call(
            "magnet:?xt=urn:btih:FAIL", save_directory="/downloads/Book", label="audiobooks"
        )
        mock_instance.add_torrent_magnet.assert_any_call("magnet:?xt=urn:btih:FAIL", save_directory="/downloads/Book")


def test_deluge_fallback_robustness_strings(app: Flask) -> None:
    """Test that the fallback works with various Deluge error messages."""
    error_variations = [
        "Unknown parameter 'label'",
        "Parameter 'label' not found",
        "Invalid argument: label",
    ]

    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value

        for error_msg in error_variations:
            mock_instance.add_torrent_magnet.reset_mock()
            mock_instance.add_torrent_magnet.side_effect = [
                Exception(error_msg),
                None,
            ]

            manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
            manager.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book")

            assert mock_instance.add_torrent_magnet.call_count == 2


def test_deluge_fallback_failure(app: Flask) -> None:
    """Test that if the Deluge fallback also fails, it raises an error."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        # Sequence:
        # 1. Attempt 1 (With Label) -> Fails "Unknown parameter"
        # 2. Attempt 1 (Fallback No Label) -> Fails "Critical Network Failure"
        # -- add_magnet wrapper catches this, logs warning, and Retries --
        # 3. Attempt 2 (With Label) -> Fails "Unknown parameter"
        # 4. Attempt 2 (Fallback No Label) -> Fails "Critical Network Failure"
        # -- Final Exception propagates out --
        mock_instance.add_torrent_magnet.side_effect = [
            Exception("Unknown parameter 'label'"),
            Exception("Critical Network Failure"),
            Exception("Unknown parameter 'label'"),
            Exception("Critical Network Failure"),
        ]

        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")

        with patch("app.clients.logger") as mock_logger:
            with pytest.raises(Exception) as exc:
                manager.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book")

            assert "Critical Network Failure" in str(exc.value)
            found = any("Deluge fallback failed" in str(call) for call in mock_logger.error.call_args_list)
            assert found


def test_deluge_add_magnet_generic_error(app: Flask) -> None:
    """Test that a generic error in Deluge addition is raised."""
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.add_torrent_magnet.side_effect = Exception("Generic Failure")
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")

        with pytest.raises(Exception) as exc:
            manager._add_magnet_logic("magnet:...", "/path")
        assert "Generic Failure" in str(exc.value)


def test_add_magnet_reconnect_retry(app: Flask) -> None:
    """Test that add_magnet attempts to reconnect if the first call fails."""
    with patch("app.clients.QbClient"):
        manager = setup_manager(app)
        # Patch the logic method to throw then succeed
        with patch.object(manager, "_add_magnet_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), None]
            manager.add_magnet("magnet:...", "/save")
            assert mock_logic.call_count == 2
            # THREAD SAFETY UPDATE: Checked threaded local instead of _client
            assert getattr(manager._local, "client", None) is None


def test_logic_methods_no_client(app: Flask) -> None:
    """Test that logic methods raise ConnectionError when client is None."""
    manager = setup_manager(app)
    # Force client to be None despite any init attempts
    with patch.object(manager, "_get_client", return_value=None):
        with pytest.raises(ConnectionError):
            manager._add_magnet_logic("magnet:...", "/path")

        with pytest.raises(ConnectionError):
            manager._get_status_logic()
