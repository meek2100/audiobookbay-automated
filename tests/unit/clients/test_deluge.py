"""Unit tests for DelugeStrategy."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from deluge_web_client.schema import Response, TorrentOptions
from flask import Flask

from audiobook_automated.clients.deluge import Strategy as DelugeStrategy


def test_deluge_add_magnet() -> None:
    """Test DelugeStrategy add_magnet."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True, error=None)
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:XYZ", "/downloads/Book", "audiobooks")

        mock_instance.login.assert_called_once()
        expected_options = TorrentOptions(download_location="/downloads/Book", label="audiobooks")
        mock_instance.add_torrent_magnet.assert_called_with("magnet:?xt=urn:btih:XYZ", torrent_options=expected_options)


def test_remove_torrent_deluge() -> None:
    """Test removing torrent for Deluge."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        strategy.remove_torrent("hash123")

        mock_instance.remove_torrent.assert_called_with("hash123", remove_data=False)


def test_deluge_label_plugin_error() -> None:
    """Test that Deluge falls back to adding torrent without label if plugin is missing."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        # Enable plugin so we try adding with label first
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)

        mock_instance.add_torrent_magnet.side_effect = [
            Exception("Unknown parameter 'label'"),
            None,
        ]

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book", "audiobooks")

        assert mock_instance.add_torrent_magnet.call_count == 2
        # 1. First call has label
        expected_full = TorrentOptions(download_location="/downloads/Book", label="audiobooks")
        mock_instance.add_torrent_magnet.assert_any_call("magnet:?xt=urn:btih:FAIL", torrent_options=expected_full)
        # 2. Second call has NO label
        expected_fallback = TorrentOptions(download_location="/downloads/Book")
        mock_instance.add_torrent_magnet.assert_any_call("magnet:?xt=urn:btih:FAIL", torrent_options=expected_fallback)


def test_deluge_fallback_failure() -> None:
    """Test that if the Deluge fallback also fails, it raises an error."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)

        mock_instance.add_torrent_magnet.side_effect = [
            Exception("Unknown parameter 'label'"),
            Exception("Critical Network Failure"),
        ]

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        with patch("audiobook_automated.clients.deluge.logger") as mock_logger:
            with pytest.raises(Exception) as exc:
                strategy.add_magnet("magnet:?xt=urn:btih:FAIL", "/downloads/Book", "audiobooks")

            assert "Critical Network Failure" in str(exc.value)
            found = any("Deluge fallback failed" in str(call) for call in mock_logger.error.call_args_list)
            assert found


def test_deluge_connect_plugin_check_failure() -> None:
    """Test handling of exception during Deluge plugin check."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        # Simulate exception during get_plugins
        mock_instance.get_plugins.side_effect = Exception("Plugin API Error")

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")

        with patch("audiobook_automated.clients.deluge.logger") as mock_logger:
            strategy.connect()

            assert strategy.label_plugin_enabled is False
            assert mock_logger.warning.called
            assert "Could not verify Deluge plugins" in str(mock_logger.warning.call_args[0])


def test_get_status_deluge() -> None:
    """Test fetching status from Deluge."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
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


def test_get_status_deluge_with_label_plugin() -> None:
    """Test fetching status from Deluge when Label plugin is enabled."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)

        mock_response = MagicMock()
        mock_response.result = {"hash123": {"name": "D Book", "state": "Dl", "progress": 45.5, "total_size": 100}}
        mock_instance.get_torrents_status.return_value = mock_response

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()
        results = strategy.get_status("my_category")

        # Verify filter_dict includes label
        mock_instance.get_torrents_status.assert_called_with(
            filter_dict={"label": "my_category"},
            keys=["name", "state", "progress", "total_size"],
        )


def test_get_status_deluge_empty_result() -> None:
    """Test handling of Deluge returning a None result payload."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        mock_response = MagicMock()
        mock_response.result = None
        mock_instance.get_torrents_status.return_value = mock_response

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        with patch("audiobook_automated.clients.deluge.logger") as mock_logger:
            results = strategy.get_status("cat")

        assert results == []
        args, _ = mock_logger.warning.call_args
        assert "Deluge returned empty or invalid" in args[0]


def test_strategy_not_connected_error_handling() -> None:
    """Ensure strategies raise ConnectionError if their client is None."""
    dg = DelugeStrategy(None, "host", 80, "u", "p")
    with pytest.raises(ConnectionError, match="Deluge client not connected"):
        dg.add_magnet("m", "p", "c")
    with pytest.raises(ConnectionError, match="Deluge client not connected"):
        dg.remove_torrent("123")
    with pytest.raises(ConnectionError, match="Deluge client not connected"):
        dg.get_status("c")


def test_init_deluge_failure(app: Flask, setup_manager: Any) -> None:
    """Test handling of Deluge login exception in manager."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        # Case: Exception raised during login call
        MockDeluge.return_value.login.side_effect = Exception("Login failed")
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")

        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            assert manager._get_strategy() is None
            mock_logger.error.assert_called()
            args, _ = mock_logger.error.call_args
            assert "Error initializing torrent client strategy" in args[0]


def test_init_deluge_auth_failure(app: Flask, setup_manager: Any) -> None:
    """Test handling of Deluge login returning failure (False) result."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        # Case: Login returns Response(result=False)
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=False, error="Bad Password")

        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")

        with patch("audiobook_automated.clients.manager.logger") as mock_logger:
            assert manager._get_strategy() is None
            mock_logger.error.assert_called()
            args, _ = mock_logger.error.call_args
            # Verify we caught the ConnectionError raised by our check
            assert "Failed to login to Deluge" in str(args[0])


def test_init_deluge_constructor_failure(app: Flask, setup_manager: Any) -> None:
    """Test handling of DelugeWebClient constructor failure."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient", side_effect=Exception("Init Error")):
        manager = setup_manager(app, DL_CLIENT="deluge", DL_URL="http://deluge:8112")
        assert manager._get_strategy() is None


def test_deluge_add_magnet_generic_error() -> None:
    """Test that a generic error in Deluge addition is raised."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)
        mock_instance.get_plugins.return_value = Response(result=["Label"], error=None)
        mock_instance.add_torrent_magnet.side_effect = Exception("Generic Failure")

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        with pytest.raises(Exception) as exc:
            strategy.add_magnet("magnet:...", "/path", "cat")
        assert "Generic Failure" in str(exc.value)


def test_deluge_add_magnet_no_label_plugin() -> None:
    """Test add_magnet when label plugin is disabled/missing."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
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


def test_deluge_add_magnet_failure_no_label() -> None:
    """Test exception propagation when add_magnet fails and plugins are disabled."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
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


def test_deluge_fallback_robustness_strings() -> None:
    """Test that the fallback works with various Deluge error messages."""
    error_variations = [
        "Unknown parameter 'label'",
        "Parameter 'label' not found",
        "Invalid argument: label",
    ]

    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
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


def test_get_status_deluge_invalid_item_type() -> None:
    """Test Deluge handling of non-dict items in the response dict."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
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


def test_get_status_deluge_robustness() -> None:
    """Test Deluge handling of None in individual torrent fields."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
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


def test_get_status_deluge_malformed_data() -> None:
    """Test Deluge handling of malformed progress data."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
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


def test_get_status_deluge_unexpected_data_type() -> None:
    """Test handling of Deluge returning a result that is not a dict."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as MockDeluge:
        mock_instance = MockDeluge.return_value
        mock_instance.login.return_value = Response(result=True)

        mock_response = MagicMock()
        mock_response.result = ["unexpected", "list"]
        mock_instance.get_torrents_status.return_value = mock_response

        strategy = DelugeStrategy("http://deluge:8112", "localhost", 8112, "admin", "pass")
        strategy.connect()

        with patch("audiobook_automated.clients.deluge.logger") as mock_logger:
            results = strategy.get_status("cat")

        assert results == []
        args, _ = mock_logger.warning.call_args
        assert "Deluge returned unexpected data type" in args[0]
        assert "list" in args[0]
