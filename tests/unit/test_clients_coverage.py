"""Additional tests to ensure 100% coverage for clients.py."""

from unittest.mock import MagicMock, patch
import pytest
from flask import Flask
from audiobook_automated.clients import TorrentManager

@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["DL_CLIENT"] = "qbittorrent"
    return app

def test_get_strategy_unsupported_coverage(app):
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

def test_remove_torrent_retry_coverage(app):
    """Test retry logic in remove_torrent."""
    manager = TorrentManager()
    manager.init_app(app)

    # Mock _get_strategy to fail first time (return None -> raises ConnectionError)
    # then succeed (return mock strategy)
    strategy_mock = MagicMock()

    with patch.object(manager, '_get_strategy') as mock_get_strat:
        mock_get_strat.side_effect = [None, strategy_mock]

        with patch("audiobook_automated.clients.logger") as mock_logger:
            manager.remove_torrent("123")

            # Verify retry log
            assert mock_logger.warning.called
            assert "Attempting to reconnect" in str(mock_logger.warning.call_args[0][0])

            # Verify _get_strategy called twice
            assert mock_get_strat.call_count == 2

            strategy_mock.remove_torrent.assert_called_with("123")

def test_get_status_retry_coverage(app):
    """Test retry logic in get_status."""
    manager = TorrentManager()
    manager.init_app(app)

    strategy_mock = MagicMock()
    strategy_mock.get_status.return_value = [{"name": "test"}]

    with patch.object(manager, '_get_strategy') as mock_get_strat:
        mock_get_strat.side_effect = [None, strategy_mock]

        with patch("audiobook_automated.clients.logger") as mock_logger:
            status = manager.get_status()

            assert status == [{"name": "test"}]

            # Verify retry log
            assert mock_logger.warning.called
            assert "Reconnecting" in str(mock_logger.warning.call_args[0][0])

            assert mock_get_strat.call_count == 2
