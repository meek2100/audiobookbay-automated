# File: tests/unit/clients/test_putio.py
"""Unit tests for Put.io client strategy."""

from unittest.mock import patch

import pytest
import requests_mock
from flask import Flask

from audiobook_automated.clients.manager import TorrentManager
from audiobook_automated.clients.putio import Strategy as PutioStrategy


def test_putio_init_defaults() -> None:
    """Test Put.io strategy initialization with default parameters."""
    strat = PutioStrategy("localhost", 443, None, None, token="sample-token")
    assert strat.token == "sample-token"
    assert strat.folder_id == "0"
    assert strat.base_url == "https://api.put.io/v2"


def test_putio_init_custom_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test Put.io strategy initialization with custom host, port, and env variables."""
    monkeypatch.setenv("PUTIO_TOKEN", "env-token")
    monkeypatch.setenv("PUTIO_FOLDER_ID", "42")

    strat = PutioStrategy("custom.putio.internal", 8443, None, None, scheme="https")
    assert strat.token == "env-token"
    assert strat.folder_id == "42"
    assert strat.base_url == "https://custom.putio.internal:8443/v2"


def test_putio_connect_success() -> None:
    """Test successful Put.io session connection."""
    strat = PutioStrategy("localhost", 443, None, "pw-token")
    strat.connect()
    assert strat.session is not None
    assert strat.session.headers.get("Authorization") == "Bearer pw-token"
    strat.close()
    assert strat.session is None


def test_putio_connect_missing_token() -> None:
    """Test that connect raises ConnectionError when no token is configured."""
    strat = PutioStrategy("localhost", 443, None, None)
    strat.token = None
    with pytest.raises(ConnectionError, match="not configured"):
        strat.connect()


def test_putio_verify_credentials() -> None:
    """Test Put.io verify_credentials method across success, failure, and exceptions."""
    strat = PutioStrategy("localhost", 443, None, "valid-token")

    with requests_mock.Mocker() as m:
        # Success case
        m.get("https://api.put.io/v2/account/info", json={"status": "OK", "info": {"username": "user"}})
        assert strat.verify_credentials() is True

        # Non-OK status in JSON
        m.get("https://api.put.io/v2/account/info", json={"status": "ERROR"})
        assert strat.verify_credentials() is False

        # HTTP error status
        m.get("https://api.put.io/v2/account/info", status_code=401)
        assert strat.verify_credentials() is False

        # Network/connection error
        m.get("https://api.put.io/v2/account/info", exc=ConnectionError("DNS failure"))
        assert strat.verify_credentials() is False

    # Failure when token is completely missing
    strat_no_token = PutioStrategy("localhost", 443, None, None)
    strat_no_token.token = None
    assert strat_no_token.verify_credentials() is False


def test_putio_add_magnet() -> None:
    """Test Put.io add_magnet across success and error conditions."""
    strat = PutioStrategy("localhost", 443, None, "valid-token", folder_id="100")

    with requests_mock.Mocker() as m:
        # Success case
        m.post("https://api.put.io/v2/transfers/add", json={"status": "OK", "transfer": {"id": 12345}})
        strat.add_magnet("magnet:?xt=urn:btih:ABC", "/tmp/save", "audiobooks")
        assert "magnet" in m.last_request.text
        assert "100" in m.last_request.text

        # HTTP status failure
        m.post("https://api.put.io/v2/transfers/add", status_code=400, text="Bad Request")
        with pytest.raises(RuntimeError, match="HTTP 400"):
            strat.add_magnet("magnet:?xt=urn:btih:ABC", "/tmp/save", "audiobooks")

        # JSON status error
        m.post(
            "https://api.put.io/v2/transfers/add",
            status_code=200,
            json={"status": "ERROR", "error_message": "Invalid magnet URI"},
        )
        with pytest.raises(RuntimeError, match="Invalid magnet URI"):
            strat.add_magnet("magnet:?xt=urn:btih:ABC", "/tmp/save", "audiobooks")

    # Client not connected when token is missing
    strat_no_token = PutioStrategy("localhost", 443, None, None)
    strat_no_token.token = None
    with pytest.raises(ConnectionError, match="not configured"):
        strat_no_token.add_magnet("magnet:...", "/tmp", "audiobooks")


def test_putio_get_status() -> None:
    """Test Put.io get_status with transfers, metadata fetching, and errors."""
    strat = PutioStrategy("localhost", 443, None, "valid-token")

    with requests_mock.Mocker() as m:
        m.get(
            "https://api.put.io/v2/transfers/list",
            json={
                "status": "OK",
                "transfers": [
                    {
                        "id": 101,
                        "name": "Book One",
                        "status": "DOWNLOADING",
                        "percent_done": 67.891,
                        "size": 52428800,
                    },
                    {
                        "id": 102,
                        "name": None,
                        "status": "IN_QUEUE",
                        "percent_done": 0,
                        "size": 0,
                    },
                ],
            },
        )
        torrents = strat.get_status("audiobooks")
        assert len(torrents) == 2
        assert torrents[0].id == "101"
        assert torrents[0].name == "Book One"
        assert torrents[0].progress == 67.89
        assert torrents[0].state == "Downloading"
        assert "50.00 MB" in torrents[0].size
        assert torrents[0].category == "audiobooks"

        assert torrents[1].id == "102"
        assert torrents[1].name == "Unknown"
        assert torrents[1].size == "fetching meta.."

        # HTTP error
        m.get("https://api.put.io/v2/transfers/list", status_code=500, text="Internal Error")
        with pytest.raises(RuntimeError, match="HTTP 500"):
            strat.get_status("audiobooks")

    # Client not connected when token is missing
    strat_no_token = PutioStrategy("localhost", 443, None, None)
    strat_no_token.token = None
    with pytest.raises(ConnectionError, match="not configured"):
        strat_no_token.get_status("audiobooks")


def test_putio_remove_torrent() -> None:
    """Test Put.io remove_torrent (cancel transfer) across success and errors."""
    strat = PutioStrategy("localhost", 443, None, "valid-token")

    with requests_mock.Mocker() as m:
        # Success
        m.post("https://api.put.io/v2/transfers/cancel", json={"status": "OK"})
        strat.remove_torrent("101")
        assert "101" in m.last_request.text

        # HTTP error
        m.post("https://api.put.io/v2/transfers/cancel", status_code=404, text="Not Found")
        with pytest.raises(RuntimeError, match="HTTP 404"):
            strat.remove_torrent("101")

        # JSON status error
        m.post(
            "https://api.put.io/v2/transfers/cancel",
            status_code=200,
            json={"status": "ERROR", "error_message": "Transfer not found"},
        )
        with pytest.raises(RuntimeError, match="Transfer not found"):
            strat.remove_torrent("101")

    # Client not connected when token is missing
    strat_no_token = PutioStrategy("localhost", 443, None, None)
    strat_no_token.token = None
    with pytest.raises(ConnectionError, match="not configured"):
        strat_no_token.remove_torrent("101")


def test_putio_manager_integration(app: Flask) -> None:
    """Test loading and interacting with PutioStrategy via TorrentManager."""
    manager = TorrentManager()
    app.config["DL_CLIENT"] = "putio"
    app.config["PUTIO_TOKEN"] = "manager-token"
    app.config["PUTIO_FOLDER_ID"] = "99"

    manager.init_app(app)
    assert isinstance(manager.strategy, PutioStrategy)
    assert manager.strategy.token == "manager-token"
    assert manager.strategy.folder_id == "99"
    assert manager.client_type == "Strategy"
