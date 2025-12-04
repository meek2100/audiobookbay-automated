from unittest.mock import MagicMock, patch

import pytest
from qbittorrentapi import LoginFailed

from app.clients import TorrentManager


@pytest.fixture
def mock_env(monkeypatch):
    """Sets up default environment variables for testing."""
    monkeypatch.setenv("DL_CLIENT", "qbittorrent")
    monkeypatch.setenv("DL_HOST", "localhost")
    monkeypatch.setenv("DL_PORT", "8080")
    monkeypatch.setenv("DL_USERNAME", "admin")
    monkeypatch.setenv("DL_PASSWORD", "admin")
    monkeypatch.setenv("DL_CATEGORY", "audiobooks")


# --- Initialization & Connection Tests ---


def test_init_with_dl_url(monkeypatch):
    """Test that DL_URL takes precedence if provided directly."""
    # This covers the logic branch in __init__ where DL_URL is already set,
    # skipping the auto-construction from host/port.
    monkeypatch.setenv("DL_CLIENT", "deluge")
    monkeypatch.setenv("DL_URL", "http://custom-url:1234")
    monkeypatch.delenv("DL_HOST", raising=False)
    monkeypatch.delenv("DL_PORT", raising=False)

    manager = TorrentManager()
    assert manager.dl_url == "http://custom-url:1234"


def test_init_deluge_success(mock_env, monkeypatch):
    """
    Test successful Deluge initialization to explicitly cover the client assignment.
    Covers app/clients.py lines 111-112.
    """
    monkeypatch.setenv("DL_CLIENT", "deluge")
    monkeypatch.setenv("DL_URL", "http://deluge:8112")
    monkeypatch.setenv("DL_PASSWORD", "pass")

    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        manager = TorrentManager()

        # Explicitly call _get_client to trigger the initialization logic
        client = manager._get_client()

        # Assertions to ensure the code path was hit
        assert client is not None
        assert manager._client == mock_instance
        # Verify login was called (Line 111)
        mock_instance.login.assert_called_once()


def test_qbittorrent_add_magnet(mock_env):
    with patch("app.clients.QbClient") as MockQbClient:
        # Setup the mock client instance
        mock_instance = MockQbClient.return_value
        mock_instance.torrents_add.return_value = "Ok."

        manager = TorrentManager()
        # Trigger the lazy loading of the client
        manager._get_client()

        manager.add_magnet("magnet:?xt=urn:btih:123", "/downloads/Book")

        # TEST: Verify client init call
        # Note: requests_args removed to fix compatibility issues
        MockQbClient.assert_called_with(
            host="localhost",
            port="8080",
            username="admin",
            password="admin",
        )

        # Verify login was called
        mock_instance.auth_log_in.assert_called_once()
        # Verify add torrent was called with correct args
        mock_instance.torrents_add.assert_called_with(
            urls="magnet:?xt=urn:btih:123", save_path="/downloads/Book", category="audiobooks"
        )


def test_qbittorrent_add_magnet_failure_response(mock_env):
    """Test logging when qBittorrent returns a failure string (Robustness coverage)."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        # Simulate a failure response string from API
        mock_instance.torrents_add.return_value = "Fails."

        manager = TorrentManager()
        manager._get_client()

        with patch("app.clients.logger") as mock_logger:
            manager.add_magnet("magnet:?xt=urn:btih:123", "/downloads/Book")

            # Verify that the code warned about the non-OK response
            args, _ = mock_logger.warning.call_args
            assert "qBittorrent add returned unexpected response" in args[0]
            assert "Fails." in args[0]


def test_transmission_add_magnet(mock_env, monkeypatch):
    monkeypatch.setenv("DL_CLIENT", "transmission")

    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        manager = TorrentManager()
        manager.add_magnet("magnet:?xt=urn:btih:ABC", "/downloads/Book")

        mock_instance.add_torrent.assert_called_with(
            "magnet:?xt=urn:btih:ABC", download_dir="/downloads/Book", labels=["audiobooks"]
        )


def test_transmission_add_magnet_fallback(mock_env, monkeypatch):
    """
    Test that Transmission falls back to adding torrent without label if first attempt fails.
    This covers the robustness logic for older Transmission daemons.
    """
    monkeypatch.setenv("DL_CLIENT", "transmission")

    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        # Simulate exception on first call (with labels), success on second call (without)
        mock_instance.add_torrent.side_effect = [TypeError("unexpected keyword argument 'labels'"), None]

        manager = TorrentManager()

        with patch("app.clients.logger") as mock_logger:
            manager.add_magnet("magnet:?xt=urn:btih:FALLBACK", "/downloads/Book")

            # Verify the warning was logged
            args, _ = mock_logger.warning.call_args
            assert "Transmission label assignment failed" in args[0]

        # Verify add_torrent was called twice
        assert mock_instance.add_torrent.call_count == 2

        # 1. First attempt with labels
        mock_instance.add_torrent.assert_any_call(
            "magnet:?xt=urn:btih:FALLBACK", download_dir="/downloads/Book", labels=["audiobooks"]
        )
        # 2. Second attempt without labels
        mock_instance.add_torrent.assert_any_call("magnet:?xt=urn:btih:FALLBACK", download_dir="/downloads/Book")


def test_transmission_add_magnet_generic_exception_fallback(mock_env, monkeypatch):
    """
    Test that Transmission falls back even on generic exceptions (not just TypeError).
    This ensures robustness against network or protocol errors during label assignment.
    """
    monkeypatch.setenv("DL_CLIENT", "transmission")

    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        # Simulate generic exception on first call, success on second
        mock_instance.add_torrent.side_effect = [Exception("Generic Protocol Error"), None]

        manager = TorrentManager()

        with patch("app.clients.logger") as mock_logger:
            manager.add_magnet("magnet:?xt=urn:btih:GENERIC", "/downloads/Book")

            # Verify the warning was logged
            args, _ = mock_logger.warning.call_args
            assert "Transmission label assignment failed" in args[0]

        # Verify add_torrent was called twice
        assert mock_instance.add_torrent.call_count == 2


def test_deluge_add_magnet(mock_env, monkeypatch):
    monkeypatch.setenv("DL_CLIENT", "deluge")

    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value

        manager = TorrentManager()
        manager.add_magnet("magnet:?xt=urn:btih:XYZ", "/downloads/Book")

        mock_instance.login.assert_called_once()
        mock_instance.add_torrent_magnet.assert_called_with(
            "magnet:?xt=urn:btih:XYZ", save_directory="/downloads/Book", label="audiobooks"
        )


def test_init_deluge_success_check(mock_env, monkeypatch):
    """Test successful Deluge initialization to cover the client assignment."""
    monkeypatch.setenv("DL_CLIENT", "deluge")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        manager = TorrentManager()

        # Explicitly call _get_client to trigger initialization
        client = manager._get_client()

        assert client is not None
        mock_instance.login.assert_called_once()
        # Verify the manager stored the client instance
        assert manager._client == mock_instance


def test_unsupported_client(mock_env, monkeypatch):
    """Test that unsupported clients return None and log error instead of crashing."""
    monkeypatch.setenv("DL_CLIENT", "fake_client")
    manager = TorrentManager()

    # Verify that the ValueError is raised inside and caught
    with patch("app.clients.logger") as mock_logger:
        client = manager._get_client()
        assert client is None

        # PROOF OF COVERAGE: Verify that logger.error was called with the exception
        # that was raised by line 111 ("Unsupported download client")
        assert mock_logger.error.called
        args, _ = mock_logger.error.call_args
        assert "Error initializing torrent client" in args[0]


def test_init_transmission_failure(monkeypatch):
    """Test handling of Transmission connection failure."""
    monkeypatch.setenv("DL_CLIENT", "transmission")
    monkeypatch.setenv("DL_HOST", "localhost")
    with patch("app.clients.TxClient") as MockTx:
        MockTx.side_effect = Exception("Connection refused")
        manager = TorrentManager()
        assert manager._get_client() is None


def test_init_deluge_failure(monkeypatch):
    """Test handling of Deluge login failure."""
    monkeypatch.setenv("DL_CLIENT", "deluge")
    monkeypatch.setenv("DL_URL", "http://deluge:8112")
    monkeypatch.setenv("DL_PASSWORD", "pass")

    with patch("app.clients.DelugeWebClient") as MockDeluge:
        # Instance created successfully, but login fails
        MockDeluge.return_value.login.side_effect = Exception("Login failed")

        # Spy on the logger to ensure the except block is hit
        with patch("app.clients.logger") as mock_logger:
            manager = TorrentManager()
            assert manager._get_client() is None

            # Assert logger was called with the specific error message
            mock_logger.error.assert_called()
            args, _ = mock_logger.error.call_args
            assert "Failed to connect to Deluge" in args[0]


def test_init_deluge_constructor_failure(monkeypatch):
    """
    Test handling of DelugeWebClient constructor failure.
    This ensures the 'try' block catches errors during instantiation.
    """
    monkeypatch.setenv("DL_CLIENT", "deluge")
    monkeypatch.setenv("DL_URL", "http://deluge:8112")

    with patch("app.clients.DelugeWebClient", side_effect=Exception("Init Error")):
        manager = TorrentManager()
        assert manager._get_client() is None


def test_init_qbittorrent_login_failed(monkeypatch):
    """Test handling of qBittorrent authentication failure."""
    monkeypatch.setenv("DL_CLIENT", "qbittorrent")
    with patch("app.clients.QbClient") as MockQb:
        MockQb.return_value.auth_log_in.side_effect = LoginFailed("Bad Auth")
        manager = TorrentManager()
        assert manager._get_client() is None


def test_verify_credentials_fail(monkeypatch):
    """Test verify_credentials returns False when client fails to init."""
    monkeypatch.setenv("DL_CLIENT", "qbittorrent")
    with patch("app.clients.TorrentManager._get_client", return_value=None):
        manager = TorrentManager()
        assert manager.verify_credentials() is False


# --- Utility Tests ---


def test_format_size_logic():
    """Verify that bytes are converted to human-readable strings correctly."""
    tm = TorrentManager
    # Standard units
    assert tm._format_size(500) == "500.00 B"
    assert tm._format_size(1024) == "1.00 KB"
    assert tm._format_size(1048576) == "1.00 MB"
    assert tm._format_size(1073741824) == "1.00 GB"

    # Petabytes (Edge case)
    # 5 * 1024^5 bytes
    huge_number = 1024 * 1024 * 1024 * 1024 * 1024 * 5
    assert "5.00 PB" in tm._format_size(huge_number)

    # Invalid inputs
    assert tm._format_size(None) == "N/A"
    assert tm._format_size("not a number") == "N/A"
    assert tm._format_size([1, 2]) == "N/A"


# --- Removal Tests ---


def test_remove_torrent_qbittorrent(mock_env):
    """Test removing torrent for qBittorrent."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value
        manager = TorrentManager()
        manager.remove_torrent("hash123")

        mock_instance.torrents_delete.assert_called_with(torrent_hashes="hash123", delete_files=False)


def test_remove_torrent_transmission_hash(mock_env, monkeypatch):
    """Test removing torrent for Transmission using a string hash."""
    monkeypatch.setenv("DL_CLIENT", "transmission")
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        manager = TorrentManager()

        # Test string ID (hash)
        manager.remove_torrent("hash123")
        mock_instance.remove_torrent.assert_called_with(ids=["hash123"], delete_data=False)


def test_remove_torrent_transmission_numeric_id(mock_env, monkeypatch):
    """Test removing torrent for Transmission with a numeric ID (int conversion path)."""
    monkeypatch.setenv("DL_CLIENT", "transmission")
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        manager = TorrentManager()

        # Test numeric string ID (should be converted to int)
        manager.remove_torrent("12345")
        # Assert the call uses the integer ID
        mock_instance.remove_torrent.assert_called_with(ids=[12345], delete_data=False)


def test_remove_torrent_transmission_int_conversion_failure(mock_env, monkeypatch):
    """
    Test removing torrent for Transmission when ID is not an integer.
    Ensures the ValueError catch block is executed.
    """
    monkeypatch.setenv("DL_CLIENT", "transmission")
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        manager = TorrentManager()

        # "not_an_int" triggers the ValueError in int(), falling back to tid="not_an_int"
        manager.remove_torrent("not_an_int")

        # Assert the call uses the string ID, proving fallback worked
        mock_instance.remove_torrent.assert_called_with(ids=["not_an_int"], delete_data=False)


def test_remove_torrent_deluge(mock_env, monkeypatch):
    """Test removing torrent for Deluge."""
    monkeypatch.setenv("DL_CLIENT", "deluge")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        manager = TorrentManager()

        manager.remove_torrent("hash123")
        mock_instance.remove_torrent.assert_called_with("hash123", remove_data=False)


def test_remove_torrent_no_client(monkeypatch):
    """Test exception when trying to remove a torrent without a valid client."""
    monkeypatch.setenv("DL_CLIENT", "transmission")
    with patch("app.clients.TxClient", side_effect=Exception("Down")):
        manager = TorrentManager()
        with pytest.raises(ConnectionError):
            manager.remove_torrent("123")


# --- Status & Info Tests ---


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


def test_get_status_qbittorrent_robustness(mock_env):
    """Test qBittorrent handling of None progress (e.g. stalled metadata)."""
    with patch("app.clients.QbClient") as MockQbClient:
        mock_instance = MockQbClient.return_value

        mock_torrent = MagicMock()
        mock_torrent.hash = "hash_bad"
        mock_torrent.name = "Stalled Book"
        mock_torrent.progress = None  # Force None
        mock_torrent.state = "metaDL"
        mock_torrent.total_size = None

        mock_instance.torrents_info.return_value = [mock_torrent]

        manager = TorrentManager()
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["progress"] == 0.0  # Should fallback
        assert results[0]["size"] == "N/A"


def test_get_status_transmission(mock_env, monkeypatch):
    """Test fetching status from Transmission."""
    monkeypatch.setenv("DL_CLIENT", "transmission")
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


def test_get_status_transmission_robustness(mock_env, monkeypatch):
    """Test fetching status from Transmission handles None values gracefully."""
    monkeypatch.setenv("DL_CLIENT", "transmission")
    with patch("app.clients.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        mock_torrent_bad = MagicMock()
        mock_torrent_bad.id = 2
        mock_torrent_bad.name = "Bad Torrent"
        mock_torrent_bad.progress = None
        mock_torrent_bad.total_size = None
        mock_torrent_bad.status = "error"

        mock_instance.get_torrents.return_value = [mock_torrent_bad]

        manager = TorrentManager()
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["name"] == "Bad Torrent"
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "N/A"


def test_get_status_deluge(monkeypatch):
    """Test fetching status from Deluge."""
    monkeypatch.setenv("DL_CLIENT", "deluge")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        mock_response.result = {"hash123": {"name": "D Book", "state": "Dl", "progress": 45.5, "total_size": 100}}
        mock_instance.get_torrents_status.return_value = mock_response
        manager = TorrentManager()
        results = manager.get_status()
        assert len(results) == 1
        assert results[0]["name"] == "D Book"


def test_get_status_deluge_empty_result(monkeypatch):
    """Test handling of Deluge returning a None result payload."""
    monkeypatch.setenv("DL_CLIENT", "deluge")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        mock_response.result = None
        mock_instance.get_torrents_status.return_value = mock_response

        manager = TorrentManager()
        with patch("app.clients.logger") as mock_logger:
            results = manager.get_status()

        assert results == []
        # Verify the warning was logged
        args, _ = mock_logger.warning.call_args
        assert "Deluge returned empty or invalid" in args[0]


def test_get_status_deluge_robustness(monkeypatch):
    """Test Deluge handling of None in individual torrent fields."""
    monkeypatch.setenv("DL_CLIENT", "deluge")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_response = MagicMock()
        mock_response.result = {
            "hash999": {"name": "Broken Book", "state": "Error", "progress": None, "total_size": None}
        }
        mock_instance.get_torrents_status.return_value = mock_response

        manager = TorrentManager()
        results = manager.get_status()

        assert len(results) == 1
        assert results[0]["name"] == "Broken Book"
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "N/A"


def test_get_status_reconnect(monkeypatch):
    """Test that get_status attempts to reconnect if the first call fails."""
    monkeypatch.setenv("DL_CLIENT", "qbittorrent")
    with patch("app.clients.QbClient"):
        manager = TorrentManager()
        with patch.object(manager, "_get_status_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), []]
            result = manager.get_status()
            assert mock_logic.call_count == 2
            assert result == []
            assert manager._client is None


# --- Error Handling & Retries ---


def test_deluge_label_plugin_error(mock_env, monkeypatch):
    """Test that Deluge falls back to adding torrent without label if plugin is missing."""
    monkeypatch.setenv("DL_CLIENT", "deluge")

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


def test_deluge_fallback_failure(mock_env, monkeypatch):
    """Test that if the Deluge fallback (retrying without label) also fails, it raises an error."""
    monkeypatch.setenv("DL_CLIENT", "deluge")

    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value

        # We provide 4 side effects because 'add_magnet' has a built-in retry mechanism.
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

        manager = TorrentManager()

        with patch("app.clients.logger") as mock_logger:
            with pytest.raises(Exception) as exc:
                manager.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book")

            assert "Critical Network Failure" in str(exc.value)
            # Verify the error log was captured for the nested failure
            found = any("Deluge fallback failed" in str(call) for call in mock_logger.error.call_args_list)
            assert found


def test_deluge_add_magnet_generic_error(monkeypatch):
    """Test that a generic error in Deluge addition is raised (not swallowed)."""
    monkeypatch.setenv("DL_CLIENT", "deluge")
    with patch("app.clients.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.add_torrent_magnet.side_effect = Exception("Generic Failure")
        manager = TorrentManager()
        with pytest.raises(Exception) as exc:
            manager._add_magnet_logic("magnet:...", "/path")
        assert "Generic Failure" in str(exc.value)


def test_add_magnet_reconnect_retry(monkeypatch):
    """Test that add_magnet attempts to reconnect if the first call fails."""
    monkeypatch.setenv("DL_CLIENT", "qbittorrent")
    with patch("app.clients.QbClient"):
        manager = TorrentManager()
        # Patch the logic method to throw then succeed
        with patch.object(manager, "_add_magnet_logic") as mock_logic:
            mock_logic.side_effect = [Exception("Stale Connection"), None]
            manager.add_magnet("magnet:...", "/save")
            assert mock_logic.call_count == 2
            assert manager._client is None


def test_logic_methods_no_client(monkeypatch):
    """Test that logic methods raise ConnectionError when client is None."""
    manager = TorrentManager()
    # Force client to be None despite any init attempts
    with patch.object(manager, "_get_client", return_value=None):
        with pytest.raises(ConnectionError):
            manager._add_magnet_logic("magnet:...", "/path")

        with pytest.raises(ConnectionError):
            manager._get_status_logic()
