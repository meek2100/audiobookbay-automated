# File: tests/unit/clients/test_manager.py
"""Unit tests for the TorrentManager."""

from unittest.mock import MagicMock, patch

from flask import Flask

from audiobook_automated.clients.base import TorrentClientStrategy
from audiobook_automated.clients.manager import TorrentManager


class MockStrategy(TorrentClientStrategy):
    def connect(self):
        pass

    def close(self):
        pass

    def add_magnet(self, link, path, category):
        pass

    def remove_torrent(self, torrent_id):
        pass

    def get_status(self, category):
        return []

    def verify_credentials(self):
        return True

    DEFAULT_PORT = 1234


def test_manager_load_strategy_success(app: Flask, caplog):
    manager = TorrentManager()

    mock_module = MagicMock()
    mock_module.MockStrategy = MockStrategy

    with patch("importlib.import_module", return_value=mock_module):
        app.config["DL_CLIENT"] = "mock_client"
        app.config["DL_HOST"] = "1.2.3.4"
        app.config["DL_PORT"] = "9999"

        manager.init_app(app)

        assert isinstance(manager.strategy, MockStrategy)
        assert manager.strategy.host == "1.2.3.4"
        assert manager.strategy.port == 9999

        assert "Successfully loaded 'MockStrategy'" in caplog.text


def test_manager_load_strategy_default_port(app: Flask, caplog):
    manager = TorrentManager()

    mock_module = MagicMock()
    mock_module.MockStrategy = MockStrategy

    with patch("importlib.import_module", return_value=mock_module):
        app.config["DL_CLIENT"] = "mock_client"
        app.config["DL_HOST"] = "1.2.3.4"
        # DL_PORT missing or None to trigger default logic
        app.config["DL_PORT"] = None

        manager.init_app(app)

        assert isinstance(manager.strategy, MockStrategy)
        assert manager.strategy.port == 1234  # MockStrategy.DEFAULT_PORT


def test_manager_load_strategy_invalid_port(app: Flask, caplog):
    manager = TorrentManager()

    mock_module = MagicMock()
    mock_module.MockStrategy = MockStrategy

    with patch("importlib.import_module", return_value=mock_module):
        app.config["DL_CLIENT"] = "mock_client"
        app.config["DL_HOST"] = "1.2.3.4"
        app.config["DL_PORT"] = "invalid"

        manager.init_app(app)

        assert isinstance(manager.strategy, MockStrategy)
        assert manager.strategy.port == 8080  # Fallback from exception block


def test_manager_load_strategy_invalid_name(app: Flask, caplog):
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "invalid$name"

    with patch("importlib.import_module") as mock_import:
        mock_import.side_effect = ImportError("Stop here")

        manager.init_app(app)

        assert "Security: Invalid DL_CLIENT name" in caplog.text
        assert "Falling back to 'transmission'" in caplog.text
        mock_import.assert_called_with("audiobook_automated.clients.transmission")


def test_manager_load_strategy_import_error(app: Flask, caplog):
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "missing_client"

    with patch("importlib.import_module", side_effect=ImportError("No module")):
        manager.init_app(app)

        assert manager.strategy is None
        assert "Failed to load client 'missing_client'" in caplog.text


def test_manager_load_strategy_no_class(app: Flask, caplog):
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "empty_client"

    mock_module = MagicMock(spec=[])

    with patch("importlib.import_module", return_value=mock_module):
        manager.init_app(app)

    assert manager.strategy is None
    assert "Failed to load client 'empty_client'" in caplog.text


def test_manager_proxy_methods_no_strategy():
    manager = TorrentManager()
    manager.strategy = None

    assert manager.verify_credentials() is False
    assert manager.add_magnet("link", "path") is None
    assert manager.get_status() == []
    assert manager.remove_torrent("id") is False
    manager.close()


def test_manager_proxy_methods_with_strategy(app: Flask):
    manager = TorrentManager()
    app.config["DL_CATEGORY"] = "abb-automated"
    manager._app = app
    strategy = MagicMock()
    manager.strategy = strategy

    strategy.verify_credentials.return_value = True
    assert manager.verify_credentials() is True

    manager.add_magnet("link", "path")
    strategy.add_magnet.assert_called_with("link", "path", "abb-automated")

    strategy.get_status.return_value = ["status"]
    assert manager.get_status() == ["status"]
    strategy.get_status.assert_called_with("abb-automated")

    strategy.remove_torrent.return_value = True
    assert manager.remove_torrent("id") is True

    # Exception handling
    strategy.remove_torrent.side_effect = Exception("Fail")
    assert manager.remove_torrent("id") is False

    manager.close()
    strategy.close.assert_called_once()


def test_manager_teardown_request():
    manager = TorrentManager()
    strategy = MagicMock()
    manager.strategy = strategy

    manager.teardown_request()

    strategy.teardown = MagicMock()
    manager.teardown_request()
    strategy.teardown.assert_called_once()


def test_manager_client_type():
    manager = TorrentManager()
    assert manager.client_type == "None"

    manager.strategy = MockStrategy("h", 1, None, None)
    assert manager.client_type == "MockStrategy"
