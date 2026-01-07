"""Unit tests for the Deluge client strategy."""

from unittest.mock import MagicMock, patch

import pytest

from audiobook_automated.clients.deluge import Strategy


@pytest.fixture
def mock_deluge_client():
    with patch("audiobook_automated.clients.deluge.DelugeWebClient") as mock:
        client_instance = mock.return_value
        # Default successful login
        client_instance.login.return_value.error = None
        # Default plugins (None)
        client_instance.get_plugins.return_value.result = []
        yield client_instance


def create_strategy(dl_url=None, host="localhost", port=8112, username=None, password=None):
    return Strategy(
        dl_url=dl_url,
        host=host,
        port=port,
        username=username,
        password=password
    )


def test_deluge_connect_success(mock_deluge_client):
    strategy = create_strategy(dl_url="http://localhost:8112", password="pass")
    strategy.connect()

    mock_deluge_client.login.assert_called_once()
    assert strategy.client is not None
    assert strategy.label_plugin_enabled is False


def test_deluge_connect_login_failure(mock_deluge_client):
    mock_deluge_client.login.return_value.error = "Invalid Password"
    strategy = create_strategy(dl_url="http://localhost:8112", password="pass")

    with pytest.raises(ConnectionError, match="Failed to login to Deluge"):
        strategy.connect()


def test_deluge_connect_with_label_plugin(mock_deluge_client):
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112", password="pass")
    strategy.connect()
    assert strategy.label_plugin_enabled is True


def test_deluge_connect_plugin_check_fail(mock_deluge_client):
    mock_deluge_client.get_plugins.side_effect = Exception("API Error")
    strategy = create_strategy()
    strategy.connect()
    assert strategy.label_plugin_enabled is False


def test_deluge_add_magnet_no_client():
    strategy = create_strategy()
    with pytest.raises(ConnectionError, match="not connected"):
        strategy.add_magnet("magnet:?", "/downloads", "audiobooks")


def test_deluge_add_magnet_with_label(mock_deluge_client):
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    strategy.add_magnet("magnet:?", "/downloads", "audiobooks")

    args, kwargs = mock_deluge_client.add_torrent_magnet.call_args
    options = kwargs['torrent_options']
    assert options.download_location == "/downloads"
    assert options.label == "audiobooks"


def test_deluge_add_magnet_fallback(mock_deluge_client):
    # Simulate Label plugin enabled but adding fails with Label error
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    # First call raises Exception about Label
    mock_deluge_client.add_torrent_magnet.side_effect = [
        Exception("Unknown parameter: label"),
        None # Second call succeeds
    ]

    strategy.add_magnet("magnet:?", "/downloads", "audiobooks")

    assert mock_deluge_client.add_torrent_magnet.call_count == 2


def test_deluge_add_magnet_fallback_fail(mock_deluge_client):
    # Fallback also fails
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.add_torrent_magnet.side_effect = [
        Exception("Unknown parameter: label"),
        Exception("Disk Full")
    ]

    with pytest.raises(Exception, match="Disk Full"):
        strategy.add_magnet("magnet:?", "/downloads", "audiobooks")


def test_deluge_add_magnet_other_error(mock_deluge_client):
    # Error NOT related to label
    mock_deluge_client.get_plugins.return_value.result = ["Label"]
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.add_torrent_magnet.side_effect = Exception("Network Error")

    with pytest.raises(Exception, match="Network Error"):
        strategy.add_magnet("magnet:?", "/downloads", "audiobooks")


def test_deluge_remove_torrent(mock_deluge_client):
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()
    strategy.remove_torrent("hash")
    mock_deluge_client.remove_torrent.assert_called_with("hash", remove_data=False)


def test_deluge_remove_torrent_no_client():
    strategy = create_strategy()
    with pytest.raises(ConnectionError, match="not connected"):
        strategy.remove_torrent("hash")


def test_deluge_get_status(mock_deluge_client):
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.get_torrents_status.return_value.result = {
        "hash1": {
            "name": "Book 1",
            "state": "Downloading",
            "progress": 50.5,
            "total_size": 1024 * 1024
        }
    }

    statuses = strategy.get_status("audiobooks")
    assert len(statuses) == 1
    assert statuses[0].id == "hash1"
    assert statuses[0].progress == 50.5
    assert statuses[0].size == "1.00 MB"


def test_deluge_get_status_no_client():
    strategy = create_strategy()
    with pytest.raises(ConnectionError, match="not connected"):
        strategy.get_status("cat")


def test_deluge_get_status_invalid_progress(mock_deluge_client):
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.get_torrents_status.return_value.result = {
        "hash1": {
            "name": "Book 1",
            "progress": "invalid",
            "state": "Error",
            "total_size": 0
        }
    }

    statuses = strategy.get_status("audiobooks")
    assert len(statuses) == 1
    assert statuses[0].progress == 0.0


def test_deluge_get_status_bad_data_structure(mock_deluge_client):
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    # result is list instead of dict
    mock_deluge_client.get_torrents_status.return_value.result = ["not a dict"]

    statuses = strategy.get_status("audiobooks")
    assert statuses == []


def test_deluge_get_status_none_result(mock_deluge_client):
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.get_torrents_status.return_value.result = None

    statuses = strategy.get_status("audiobooks")
    assert statuses == []


def test_deluge_get_status_null_item(mock_deluge_client):
    strategy = create_strategy(dl_url="http://localhost:8112")
    strategy.connect()

    mock_deluge_client.get_torrents_status.return_value.result = {
        "hash1": None
    }

    statuses = strategy.get_status("audiobooks")
    assert statuses == []


def test_deluge_close():
    strategy = create_strategy()
    strategy.client = MagicMock()
    strategy.close()
    assert strategy.client is None
