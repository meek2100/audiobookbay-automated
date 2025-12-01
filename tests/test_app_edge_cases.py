import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

import app.app as app_module  # Fix: Import for reliable monkeypatching


@pytest.fixture
def mock_flask_factory():
    """Patches Flask class to return a mock app with a traceable logger and config."""
    with patch("flask.Flask") as mock_class:
        mock_app = MagicMock()
        mock_logger = MagicMock()
        mock_app.logger = mock_logger
        # config must be a real dict so extensions like limiter don't crash
        mock_app.config = {}
        mock_class.return_value = mock_app
        yield mock_class, mock_logger


def test_app_startup_verification_fail(monkeypatch, mock_flask_factory):
    """Test that app handles verify_credentials failure gracefully at startup."""
    _, mock_logger = mock_flask_factory

    # Enable IS_TESTING=False to trigger the check logic
    monkeypatch.setenv("TESTING", "0")
    monkeypatch.setenv("SAVE_PATH_BASE", "/tmp")

    # FIX: Patch the class where it is DEFINED, not where it is imported.
    # When app.app reloads, it imports TorrentManager from app.clients.
    with patch("app.clients.TorrentManager") as MockTM:
        MockTM.return_value.verify_credentials.side_effect = Exception("Auth Bad")

        # Reload sys.modules["app.app"] to re-run the top-level code
        importlib.reload(sys.modules["app.app"])

        # Should have logged an error but not crashed
        args, _ = mock_logger.error.call_args
        assert "STARTUP WARNING" in args[0]
        assert "Auth Bad" in str(args[0])


def test_reload_library_detailed_error(client, monkeypatch):
    """Test /reload_library when requests raises an error WITH a response object."""
    # HERMENEUTIC FIX: Patch the module object directly using the imported module
    monkeypatch.setattr(app_module, "LIBRARY_RELOAD_ENABLED", True)

    with (
        patch("app.app.AUDIOBOOKSHELF_URL", "http://abs"),
        patch("app.app.ABS_KEY", "k"),
        patch("app.app.ABS_LIB", "l"),
    ):
        with patch("app.app.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_resp.reason = "Service Unavailable"
            mock_resp.text = "Busy"

            exc = requests.exceptions.RequestException("Request Failed")
            exc.response = mock_resp
            mock_post.side_effect = exc

            response = client.post("/reload_library")
            assert response.status_code == 500
            assert "503 Service Unavailable" in response.json["message"]


def test_status_route_error(client):
    """Test /status route when client raises generic exception."""
    with patch("app.app.torrent_manager") as mock_tm:
        mock_tm.get_status.side_effect = Exception("Database Locked")

        response = client.get("/status")
        assert response.status_code == 200
        assert b"Error connecting to client" in response.data
        assert b"Database Locked" in response.data


def test_send_route_no_save_path_base(client, monkeypatch):
    """Test the 'else' branch where SAVE_PATH_BASE is None (logic coverage)."""
    # Note: app.app.SAVE_PATH_BASE is loaded at import.
    # HERMENEUTIC FIX: Patch the module object directly using the imported module
    monkeypatch.setattr(app_module, "SAVE_PATH_BASE", None)

    with patch("app.app.extract_magnet_link", return_value=("magnet:...", None)):
        with patch("app.app.torrent_manager") as mock_tm:
            response = client.post("/send", json={"link": "l", "title": "t"})
            assert response.status_code == 200
            mock_tm.add_magnet.assert_called_with("magnet:...", "t")
