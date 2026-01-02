# File: tests/unit/clients/test_transmission.py
"""Unit tests for TransmissionStrategy."""

from unittest.mock import MagicMock, patch

import pytest

from audiobook_automated.clients.transmission import Strategy as TransmissionStrategy


def test_transmission_add_magnet() -> None:
    """Test TransmissionStrategy add_magnet."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:DEF", "/downloads/Book", "audiobooks")

        mock_instance.add_torrent.assert_called_with(
            "magnet:?xt=urn:btih:DEF", download_dir="/downloads/Book", labels=["audiobooks"]
        )


def test_transmission_add_magnet_fallback() -> None:
    """Test Transmission fallback for older versions without labels."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        # Simulate label error on first call
        mock_instance.add_torrent.side_effect = [
            Exception("Invalid argument: labels"),
            None,  # Success on second call
        ]

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        strategy.add_magnet("magnet:?xt=urn:btih:DEF", "/downloads/Book", "audiobooks")

        assert mock_instance.add_torrent.call_count == 2
        # First call has labels
        mock_instance.add_torrent.assert_any_call(
            "magnet:?xt=urn:btih:DEF", download_dir="/downloads/Book", labels=["audiobooks"]
        )
        # Second call has NO labels
        mock_instance.add_torrent.assert_any_call("magnet:?xt=urn:btih:DEF", download_dir="/downloads/Book")


def test_transmission_add_magnet_generic_error() -> None:
    """Test Transmission re-raises generic errors."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value
        mock_instance.add_torrent.side_effect = Exception("Disk Full")

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()

        with pytest.raises(Exception) as exc:
            strategy.add_magnet("magnet:...", "/path", "cat")
        assert "Disk Full" in str(exc.value)


def test_remove_torrent_transmission_int_id() -> None:
    """Test removing torrent with integer ID."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("123")

        mock_instance.remove_torrent.assert_called_with(ids=[123], delete_data=False)


def test_remove_torrent_transmission_hash_id() -> None:
    """Test removing torrent with hash ID."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        strategy.remove_torrent("hash123")

        mock_instance.remove_torrent.assert_called_with(ids=["hash123"], delete_data=False)


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
        assert results[0].progress == 75.0
        assert results[0].size == "1.00 KB"


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
        assert results[0].name == "Bad Torrent"
        assert results[0].progress == 0.0
        assert results[0].size == "Unknown"


def test_get_status_transmission_filtering() -> None:
    """Test client-side filtering by label."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        mock_instance = MockTxClient.return_value

        t1 = MagicMock(id=1, labels=["cat1"])
        t1.name = "T1"
        t2 = MagicMock(id=2, labels=["cat2"])
        t2.name = "T2"

        # Mock status/progress for robustness
        t1.status.name = "dl"
        t1.progress = 10
        t1.total_size = 100
        t2.status.name = "dl"
        t2.progress = 20
        t2.total_size = 200

        mock_instance.get_torrents.return_value = [t1, t2]

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        results = strategy.get_status("cat1")

        assert len(results) == 1
        assert results[0].name == "T1"


def test_transmission_close() -> None:
    """Test closing Transmission strategy."""
    with patch("audiobook_automated.clients.transmission.TxClient") as MockTxClient:
        # Mock successful connection
        MockTxClient.return_value = MagicMock()

        strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
        strategy.connect()
        assert strategy.client is not None
        strategy.close()
        assert strategy.client is None


def test_transmission_not_connected() -> None:
    """Test errors when client is not connected."""
    strategy = TransmissionStrategy("localhost", 9091, "admin", "admin")
    # Do NOT connect

    with pytest.raises(ConnectionError, match="Transmission client not connected"):
        strategy.add_magnet("magnet:...", "/path", "cat")

    with pytest.raises(ConnectionError, match="Transmission client not connected"):
        strategy.remove_torrent("123")

    with pytest.raises(ConnectionError, match="Transmission client not connected"):
        strategy.get_status("cat")
