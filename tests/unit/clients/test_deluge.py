# File: tests/unit/clients/test_deluge.py
"""Unit tests for the Deluge client strategy."""

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from audiobook_automated.clients.deluge import Strategy


@pytest.fixture
def mock_deluge_client() -> Generator[MagicMock]:
    """Fixture for mocking the Deluge client."""
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as mock:
        client_instance = mock.return_value
        # Default successful login
        client_instance.login.return_value.error = None
        # Default plugins (None)
        client_instance.get_plugins.return_value.result = []
        yield client_instance


def create_strategy(
    dl_url: str | None = None,
    host: str = "localhost",
    port: int = 8112,
    username: str | None = None,
    password: str | None = None,
) -> Strategy:
    """Create a strategy instance for testing."""
    return Strategy(dl_url=dl_url, host=host, port=port, username=username, password=password)


def test_deluge_connect_success(mock_deluge_client: MagicMock) -> None:
    """Test successful connection."""
    strategy = create_strategy(dl_url="http://localhost:8112", password="pass")
    strategy.connect()

    mock_deluge_client.login.assert_called_once()
    assert strategy.client is not None
    assert strategy.label_plugin_enabled is False


def test_deluge_connect_login_failure(mock_deluge_client: MagicMock) -> None:
    """Test login failure."""
    # Ensure this triggers line 80
    mock_deluge_client.login.return_value.error = "Invalid Password"
    strategy = create_strategy(dl_url="http://localhost:8112", password="pass")

    with pytest.raises(ConnectionError, match="Failed to login to Deluge"):
        strategy.connect()


def test_deluge_connect_with_label_plugin(mock_deluge_client: MagicMock) -> None:
    """Test connection with label plugin enabled."""
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112", password="pass")
    strategy.connect()
    assert strategy.label_plugin_enabled is True


def test_deluge_connect_plugin_check_fail(mock_deluge_client: MagicMock) -> None:
    """Test plugin check failure."""
    mock_deluge_client.get_plugins.side_effect = Exception("API Error")
    strategy = create_strategy()
    strategy.connect()
    assert strategy.label_plugin_enabled is False


def test_deluge_add_magnet_no_client() -> None:
    """Test adding magnet with no client connected."""
    strategy = create_strategy()
    with pytest.raises(ConnectionError, match="not connected"):
        strategy.add_magnet("magnet:?", "/downloads", "audiobooks")


def test_deluge_add_magnet_with_label(mock_deluge_client: MagicMock) -> None:
    """Test adding magnet with label."""
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    strategy.add_magnet("magnet:?", "/downloads", "audiobooks")

    _, kwargs = mock_deluge_client.add_torrent_magnet.call_args
    options = kwargs["torrent_options"]
    assert options.download_location == "/downloads"
    assert options.label == "audiobooks"


def test_deluge_add_magnet_fallback(mock_deluge_client: MagicMock) -> None:
    """Test adding magnet fallback logic."""
    # Simulate Label plugin enabled but adding fails with Label error
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    # First call raises Exception about Label
    mock_deluge_client.add_torrent_magnet.side_effect = [
        Exception("Unknown parameter: label"),
        None,  # Second call succeeds
    ]

    strategy.add_magnet("magnet:?", "/downloads", "audiobooks")

    assert mock_deluge_client.add_torrent_magnet.call_count == 2


def test_deluge_add_magnet_fallback_fail(mock_deluge_client: MagicMock) -> None:
    """Test adding magnet fallback failure."""
    # Fallback also fails
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    # Need to trigger exception inside the fallback block (lines 118-122)
    mock_deluge_client.add_torrent_magnet.side_effect = [
        Exception("Unknown parameter: label"),  # First call fails (triggers fallback)
        Exception("Disk Full"),  # Second call fails (fallback exception)
    ]

    with pytest.raises(Exception, match="Disk Full"):
        strategy.add_magnet("magnet:?", "/downloads", "audiobooks")


def test_deluge_add_magnet_other_error(mock_deluge_client: MagicMock) -> None:
    """Test adding magnet with other error."""
    # Error NOT related to label
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.add_torrent_magnet.side_effect = Exception("Network Error")

    with pytest.raises(Exception, match="Network Error"):
        strategy.add_magnet("magnet:?", "/downloads", "audiobooks")


def test_deluge_remove_torrent(mock_deluge_client: MagicMock) -> None:
    """Test removing torrent."""
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()
    strategy.remove_torrent("hash")
    mock_deluge_client.remove_torrent.assert_called_with("hash", remove_data=False)


def test_deluge_remove_torrent_no_client() -> None:
    """Test removing torrent with no client."""
    strategy = create_strategy()
    with pytest.raises(ConnectionError, match="not connected"):
        strategy.remove_torrent("hash")


def test_deluge_get_status(mock_deluge_client: MagicMock) -> None:
    """Test getting status."""
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.get_torrents_status.return_value.result = {
        "hash1": {"name": "Book 1", "state": "Downloading", "progress": 50.5, "total_size": 1024 * 1024}
    }

    statuses = strategy.get_status("audiobooks")
    assert len(statuses) == 1
    assert statuses[0].id == "hash1"
    assert statuses[0].progress == 50.5
    assert statuses[0].size == "1.00 MB"


def test_deluge_get_status_no_client() -> None:
    """Test getting status with no client."""
    strategy = create_strategy()
    with pytest.raises(ConnectionError, match="not connected"):
        strategy.get_status("cat")


def test_deluge_get_status_invalid_progress(mock_deluge_client: MagicMock) -> None:
    """Test getting status with invalid progress."""
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.get_torrents_status.return_value.result = {
        "hash1": {"name": "Book 1", "progress": "invalid", "state": "Error", "total_size": 0}
    }

    statuses = strategy.get_status("audiobooks")
    assert len(statuses) == 1
    assert statuses[0].progress == 0.0


def test_deluge_get_status_bad_data_structure(mock_deluge_client: MagicMock) -> None:
    """Test getting status with bad data structure."""
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    # result is list instead of dict
    mock_deluge_client.get_torrents_status.return_value.result = ["not a dict"]

    statuses = strategy.get_status("audiobooks")
    assert statuses == []


def test_deluge_get_status_none_result(mock_deluge_client: MagicMock) -> None:
    """Test getting status with none result."""
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.get_torrents_status.return_value.result = None

    statuses = strategy.get_status("audiobooks")
    assert statuses == []


def test_deluge_get_status_null_item(mock_deluge_client: MagicMock) -> None:
    """Test getting status with null item."""
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.get_torrents_status.return_value.result = {"hash1": None}

    statuses = strategy.get_status("audiobooks")
    assert statuses == []


def test_deluge_close() -> None:
    """Test closing connection."""
    strategy = create_strategy()
    strategy.client = MagicMock()
    strategy.close()
    assert strategy.client is None
