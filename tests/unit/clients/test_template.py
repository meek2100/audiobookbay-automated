# File: tests/unit/clients/test_template.py
"""Unit tests for the client template module."""

import pytest

from audiobook_automated.clients.base import TorrentClientStrategy
from audiobook_automated.clients.client_template import Strategy


def test_template_structure() -> None:
    """Ensure the template strategy follows the required interface."""
    assert issubclass(Strategy, TorrentClientStrategy)
    assert hasattr(Strategy, "DEFAULT_PORT")
    assert Strategy.DEFAULT_PORT == 0000


def test_template_initialization() -> None:
    """Ensure the template can be initialized."""
    # FIX: Added required username and password arguments
    strategy = Strategy(host="localhost", port=8080, username="user", password="pass")
    assert strategy.host == "localhost"
    assert strategy.port == 8080
    assert strategy.client is None


def test_template_raises_not_implemented() -> None:
    """Ensure all abstract methods raise NotImplementedError in the template."""
    # FIX: Added required username and password arguments
    strategy = Strategy(host="localhost", port=8080, username="user", password="pass")

    # Mimic a connection for methods that check self.client
    strategy.client = True

    with pytest.raises(NotImplementedError):
        strategy.connect()

    with pytest.raises(NotImplementedError):
        strategy.add_magnet("magnet:?", "/tmp", "audiobooks")

    with pytest.raises(NotImplementedError):
        strategy.remove_torrent("12345")


def test_template_get_status_returns_empty() -> None:
    """Ensure get_status returns empty list by default (or raises if not implemented)."""
    # FIX: Added required username and password arguments
    strategy = Strategy(host="localhost", port=8080, username="user", password="pass")
    strategy.client = True

    # The template implementation in the provided file actually returns []
    assert strategy.get_status("cat") == []


def test_template_methods_raise_connection_error_when_disconnected() -> None:
    """Ensure methods raise ConnectionError if client is None."""
    # FIX: Added required username and password arguments
    strategy = Strategy(host="localhost", port=8080, username="user", password="pass")
    strategy.client = None

    with pytest.raises(ConnectionError, match="Client not connected"):
        strategy.add_magnet("magnet:?", "/tmp", "cat")

    with pytest.raises(ConnectionError, match="Client not connected"):
        strategy.remove_torrent("123")

    with pytest.raises(ConnectionError, match="Client not connected"):
        strategy.get_status("cat")


def test_template_close_is_safe() -> None:
    """Ensure close() does not crash even if client is None."""
    # FIX: Added required username and password arguments
    strategy = Strategy(host="localhost", port=8080, username="user", password="pass")
    strategy.close()  # Should not raise
