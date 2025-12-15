"""Unit tests for TransmissionStrategy."""

from unittest.mock import MagicMock, patch

import pytest

from audiobook_automated.clients.transmission import Strategy as TransmissionStrategy


def test_transmission_add_magnet() -> None:
    """Test that TransmissionStrategy correctly calls the underlying client."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:ABC", "/downloads/Book", "audiobooks")

        mock_instance.add_torrent.assert_called_with(
            "magnet:?xt=urn:btih:ABC", download_dir="/downloads/Book", labels=["audiobooks"]
        )


def test_transmission_add_magnet_fallback() -> None:
    """Test that transmission falls back to adding torrent without label if first attempt fails."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        mock_instance.add_torrent.side_effect = [TypeError("unexpected keyword argument 'labels'"), None]

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        with patch("audiobook_automated.clients.transmission.logger") as mock_logger:
            strategy.add_magnet("magnet:?xt=urn:btih:FALLBACK", "/downloads/Book", "audiobooks")
            assert mock_logger.warning.called
            args, _ = mock_logger.warning.call_args
            assert "Transmission label assignment failed" in args[0]

        assert mock_instance.add_torrent.call_count == 2


def test_transmission_add_magnet_generic_exception_fallback() -> None:
    """Test that Transmission falls back even on generic exceptions."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        mock_instance.add_torrent.side_effect = [Exception("Generic Protocol Error"), None]

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        with patch("audiobook_automated.clients.transmission.logger") as mock_logger:
            strategy.add_magnet("magnet:?xt=urn:btih:GENERIC", "/downloads/Book", "audiobooks")
            args, _ = mock_logger.warning.call_args
            assert "Transmission label assignment failed" in args[0]

        assert mock_instance.add_torrent.call_count == 2


def test_remove_torrent_transmission_hash() -> None:
    """Test removing torrent for Transmission using a string hash."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("hash123")

        mock_instance.remove_torrent.assert_called_with(ids=["hash123"], delete_data=False)


def test_remove_torrent_transmission_numeric_id() -> None:
    """Test removing torrent for Transmission with a numeric ID."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("12345")

        mock_instance.remove_torrent.assert_called_with(ids=[12345], delete_data=False)


def test_remove_torrent_transmission_int_conversion_failure() -> None:
    """Test removing torrent for Transmission when ID is not an integer."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("not_an_int")

        mock_instance.remove_torrent.assert_called_with(ids=["not_an_int"], delete_data=False)


def test_get_status_transmission() -> None:
    """Test fetching status from Transmission."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        mock_torrent = MagicMock()
        mock_torrent.id = 1
        mock_torrent.name = "Test Book"
        mock_torrent.progress = 75.0
        mock_status = MagicMock()
        mock_status.name = "downloading"
        mock_torrent.status = mock_status
        mock_torrent.total_size = 1024
        mock_torrent.labels = ["cat"]

        mock_instance.get_torrents.return_value = [mock_torrent]

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0]["progress"] == 75.0
        assert results[0]["size"] == "1.00 KB"


def test_get_status_transmission_robustness() -> None:
    """Test fetching status from Transmission handles None values gracefully."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        mock_torrent_bad = MagicMock()
        mock_torrent_bad.id = 2
        mock_torrent_bad.name = "Bad Torrent"
        mock_torrent_bad.progress = None
        mock_torrent_bad.total_size = None
        mock_status_bad = MagicMock()
        mock_status_bad.name = "error"
        mock_torrent_bad.status = mock_status_bad
        mock_torrent_bad.labels = ["cat"]

        mock_instance.get_torrents.return_value = [mock_torrent_bad]

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        results = strategy.get_status("cat")

        assert len(results) == 1
        assert results[0]["name"] == "Bad Torrent"
        assert results[0]["progress"] == 0.0
        assert results[0]["size"] == "Unknown"


def test_transmission_close() -> None:
    """Test closing the Transmission session."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        # Note: We don't need the return value here, just the class patch to succeed
        strategy = TransmissionStrategy("localhost", 8080, "admin", "admin")
        strategy.connect()

        # Manually ensure client is set (it should be via connect, but we assert it)
        assert strategy.client is not None

        # Execute close
        strategy.close()

        # Assertion for coverage: The line 'self.client = None' must have run
        assert strategy.client is None


def test_strategy_not_connected_error_handling() -> None:
    """Ensure strategies raise ConnectionError if their client is None."""
    tx = TransmissionStrategy("host", 80, "u", "p")
    with pytest.raises(ConnectionError, match="Transmission client not connected"):
        tx.add_magnet("m", "p", "c")
    with pytest.raises(ConnectionError, match="Transmission client not connected"):
        tx.remove_torrent("123")
    with pytest.raises(ConnectionError, match="Transmission client not connected"):
        tx.get_status("c")
