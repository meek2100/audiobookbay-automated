# File: tests/unit/clients/test_manager.py
"""Unit tests for the TorrentManager."""

from typing import Any, cast
from unittest.mock import MagicMock, patch

from flask import Flask
from pytest import LogCaptureFixture

from audiobook_automated.clients.base import TorrentClientStrategy, TorrentStatus
from audiobook_automated.clients.manager import TorrentManager


class MockStrategy(TorrentClientStrategy):
    """Mock strategy for testing."""

    def connect(self) -> None:
        """Mock connect."""
        pass

    def close(self) -> None:
        """Mock close."""
        pass

    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        """Mock add_magnet."""
        pass

    def remove_torrent(self, torrent_id: str) -> None:
        """Mock remove_torrent."""
        pass

    def get_status(self, category: str) -> list[TorrentStatus]:
        """Mock get_status."""
        return []

    def verify_credentials(self) -> bool:
        """Mock verify_credentials."""
        return True

    DEFAULT_PORT = 1234


def test_manager_load_strategy_success(app: Flask, caplog: LogCaptureFixture) -> None:
    """Test successful strategy loading."""
    import logging

    caplog.set_level(logging.INFO)
    manager = TorrentManager()

    mock_module = MagicMock()
    mock_module.MockStrategy = MockStrategy

    with patch("importlib.import_module", return_value=mock_module):
        app.config["DL_CLIENT"] = "mock_client"
        app.config["DL_HOST"] = "1.2.3.4"
        app.config["DL_PORT"] = "9999"
        app.config["DL_USERNAME"] = "testuser"
        app.config["DL_PASSWORD"] = "testpass"

        manager.init_app(app)

        assert isinstance(manager.strategy, MockStrategy)
        assert manager.strategy.host == "1.2.3.4"
        assert manager.strategy.port == 9999
        assert manager.strategy.username == "testuser"
        assert manager.strategy.password == "testpass"

        assert "Successfully loaded 'mock_client'" in caplog.text


def test_manager_load_strategy_default_port(app: Flask, caplog: LogCaptureFixture) -> None:
    """Test default port loading."""
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


def test_manager_load_strategy_invalid_port(app: Flask, caplog: LogCaptureFixture) -> None:
    """Test invalid port loading."""
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


def test_manager_load_strategy_invalid_name(app: Flask, caplog: LogCaptureFixture) -> None:
    """Test invalid client name."""
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "invalid$name"

    with patch("importlib.import_module") as mock_import:
        mock_import.side_effect = ImportError("Stop here")

        manager.init_app(app)

        assert "Security: Invalid DL_CLIENT name" in caplog.text
        assert "Falling back to 'transmission'" in caplog.text
        mock_import.assert_called_with("audiobook_automated.clients.transmission")


def test_manager_load_strategy_import_error(app: Flask, caplog: LogCaptureFixture) -> None:
    """Test strategy import error."""
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "missing_client"

    with patch("importlib.import_module", side_effect=ImportError("No module")):
        manager.init_app(app)

        assert manager.strategy is None
        assert "Failed to load client 'missing_client'" in caplog.text


def test_manager_load_strategy_no_class(app: Flask, caplog: LogCaptureFixture) -> None:
    """Test strategy with no class."""
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "empty_client"

    mock_module = MagicMock(spec=[])

    with patch("importlib.import_module", return_value=mock_module):
        manager.init_app(app)

    assert manager.strategy is None
    assert "Failed to load client 'empty_client'" in caplog.text


def test_manager_proxy_methods_no_strategy() -> None:
    """Test proxy methods with no strategy."""
    manager = TorrentManager()
    manager.strategy = None

    assert manager.verify_credentials() is False
    # Don't assert None return for void function to satisfy Mypy
    manager.add_magnet("link", "path")
    assert manager.get_status() == []
    assert manager.remove_torrent("id") is False
    manager.close()


def test_manager_proxy_methods_with_strategy(app: Flask) -> None:
    """Test proxy methods with strategy."""
    manager = TorrentManager()
    app.config["DL_CATEGORY"] = "abb-automated"
    # Access private member via public method or fixture?
    # Or just ignore lint for test
    manager._app = app  # pyright: ignore[reportPrivateUsage]

    strategy = MagicMock()
    manager.strategy = strategy

    strategy.verify_credentials.return_value = True
    assert manager.verify_credentials() is True

    manager.add_magnet("link", "path")
    # Verify add_magnet called. It returns None so we check assertion side effect only.
    strategy.add_magnet.assert_called_with("link", "path", "abb-automated")

    strategy.get_status.return_value = ["status"]
    # We use cast(Any, ...) to bypass Mypy's strict check on return type vs string list comparison
    assert cast(Any, manager.get_status()) == ["status"]
    strategy.get_status.assert_called_with("abb-automated")

    strategy.remove_torrent.return_value = True
    assert manager.remove_torrent("id") is True

    # Exception handling
    strategy.remove_torrent.side_effect = Exception("Fail")
    assert manager.remove_torrent("id") is False

    manager.close()
    strategy.close.assert_called_once()


def test_manager_teardown_request() -> None:
    """Test teardown request."""
    manager = TorrentManager()
    strategy = MagicMock()
    manager.strategy = strategy

    manager.teardown_request()

    strategy.teardown = MagicMock()
    manager.teardown_request()
    strategy.teardown.assert_called_once()


def test_manager_client_type() -> None:
    """Test client type."""
    manager = TorrentManager()
    assert manager.client_type == "None"

    manager.strategy = MockStrategy("h", 1, None, None)
    assert manager.client_type == "MockStrategy"


def test_manager_multi_client_loading(app: Flask, caplog: LogCaptureFixture) -> None:
    """Test loading multiple clients via DL_CLIENTS."""
    manager = TorrentManager()

    mock_module = MagicMock()
    mock_module.MockStrategy = MockStrategy

    with patch("importlib.import_module", return_value=mock_module):
        app.config["DL_CLIENT"] = "client_a"
        app.config["DL_CLIENTS"] = "client_a, client_b"

        manager.init_app(app)

        assert len(manager.clients) == 2
        assert "client_a" in manager.clients
        assert "client_b" in manager.clients
        assert manager.list_clients() == ["client_a", "client_b"]
        assert manager.get_client("client_a") is not None
        assert manager.get_client("client_b") is not None
        assert manager.get_client("nonexistent") == manager.strategy


def test_manager_multi_client_add_and_status(app: Flask) -> None:
    """Test adding magnet and querying status across multiple clients."""
    manager = TorrentManager()
    app.config["DL_CATEGORY"] = "abb-automated"
    manager._app = app  # pyright: ignore[reportPrivateUsage]

    strat_a = MagicMock()
    strat_b = MagicMock()
    strat_a.get_status.return_value = [
        TorrentStatus(id="1", name="Book A", progress=50.0, state="downloading", size="500MB")
    ]
    strat_b.get_status.return_value = [
        TorrentStatus(id="2", name="Book B", progress=100.0, state="seeding", size="1GB")
    ]
    strat_a.verify_credentials.return_value = True
    strat_b.verify_credentials.return_value = False

    manager.clients = {"client_a": strat_a, "client_b": strat_b}
    manager.strategy = strat_a

    # Verify credentials targeted
    assert manager.verify_credentials("client_a") is True
    assert manager.verify_credentials("client_b") is False

    # Targeted add_magnet
    manager.add_magnet("magnet:?xt=test", "/save/path", client_name="client_b")
    strat_b.add_magnet.assert_called_with("magnet:?xt=test", "/save/path", "abb-automated")
    strat_a.add_magnet.assert_not_called()

    # Aggregated status (no filter)
    all_statuses = manager.get_status()
    assert len(all_statuses) == 2
    assert all_statuses[0].client == "client_a"
    assert all_statuses[1].client == "client_b"

    # Filtered status
    status_a = manager.get_status(client_name="client_a")
    assert len(status_a) == 1
    assert status_a[0].name == "Book A"

    # Multi-client removal across clients
    strat_b.remove_torrent.side_effect = Exception("Not here")
    strat_a.remove_torrent.return_value = True
    assert manager.remove_torrent("1") is True

    # Multi-client teardown and close
    manager.close()
    strat_a.close.assert_called_once()
    strat_b.close.assert_called_once()
    manager.teardown_request()
    strat_a.teardown.assert_called_once()
    strat_b.teardown.assert_called_once()


def test_manager_multi_client_aggregation_error(app: Flask) -> None:
    """Test get_status logs warning when one client errors during aggregation."""
    manager = TorrentManager()
    manager._app = app  # pyright: ignore[reportPrivateUsage]

    strat_good = MagicMock()
    strat_good.get_status.return_value = [
        TorrentStatus(id="1", name="Good Book", progress=10.0, state="downloading", size="10MB")
    ]
    strat_bad = MagicMock()
    strat_bad.get_status.side_effect = RuntimeError("Client unreachable")

    manager.clients = {"good": strat_good, "bad": strat_bad}
    manager.strategy = strat_good

    statuses = manager.get_status()
    assert len(statuses) == 1
    assert statuses[0].name == "Good Book"
    assert statuses[0].client == "good"


def test_manager_primary_fallback(app: Flask) -> None:
    """Test manager selects first available client if DL_CLIENT not in clients."""
    manager = TorrentManager()

    mock_module = MagicMock()
    mock_module.MockStrategy = MockStrategy

    def mock_import(name: str) -> Any:
        if "client_a" in name:
            return mock_module
        raise ImportError(f"No module {name}")

    with patch("importlib.import_module", side_effect=mock_import):
        app.config["DL_CLIENT"] = "unsupported_client"
        app.config["DL_CLIENTS"] = "client_a"

        manager.init_app(app)
        assert manager.strategy is not None
        assert "client_a" in manager.clients
        assert manager.strategy == manager.clients["client_a"]


def test_manager_status_single_client_tagging(app: Flask) -> None:
    """Test get_status populates client attribute when only one client configured."""
    manager = TorrentManager()
    manager._app = app  # pyright: ignore[reportPrivateUsage]
    strategy_instance = MagicMock()
    strategy_instance.get_status.return_value = [
        TorrentStatus(id="1", name="Single Book", progress=100.0, state="seeding", size="1GB")
    ]
    manager.strategy = strategy_instance
    manager.clients = {"qbittorrent": strategy_instance}

    statuses = manager.get_status()
    assert len(statuses) == 1
    assert statuses[0].client is not None


def test_manager_remove_torrent_fallback_loop(app: Flask) -> None:
    """Test remove_torrent iterates across clients when client_name is None and strategy has no target."""
    manager = TorrentManager()
    strat_a = MagicMock()
    strat_b = MagicMock()
    strat_a.remove_torrent.side_effect = RuntimeError("Not found")
    strat_b.remove_torrent.return_value = True

    manager.clients = {"a": strat_a, "b": strat_b}
    manager.strategy = None

    assert manager.remove_torrent("hash123") is True
    strat_a.remove_torrent.assert_called_once_with("hash123")
    strat_b.remove_torrent.assert_called_once_with("hash123")

    strat_b.remove_torrent.side_effect = RuntimeError("Failed too")
    assert manager.remove_torrent("hash456") is False
