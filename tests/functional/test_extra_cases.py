# File: tests/functional/test_extra_cases.py
"""Additional tests to ensure 100% coverage and Python 3.13+ compliance."""

from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient

from audiobook_automated.routes import construct_safe_save_path


def test_search_audiobookbay_exception_handling(client: FlaskClient) -> None:
    """Test search endpoint handling generic exceptions from scraper."""
    with patch("audiobook_automated.routes.search_audiobookbay", side_effect=Exception("Unexpected Error")):
        response = client.get("/?query=test")
        assert response.status_code == 200
        assert b"Search Failed: Unexpected Error" in response.data


def test_dl_client_import_error(client: FlaskClient) -> None:
    """Test TorrentManager logs error on valid name but missing module."""
    from audiobook_automated.extensions import torrent_manager
    from audiobook_automated.clients.manager import logger as manager_logger

    with patch.object(manager_logger, "error") as mock_log:
        # Simulate missing module
        with patch("importlib.import_module", side_effect=ImportError("Import broken")):
            torrent_manager._load_strategy_class("valid_but_broken")
            mock_log.assert_called_with("Error importing client plugin 'valid_but_broken': Import broken")


def test_construct_safe_save_path_very_long_base(client: FlaskClient) -> None:
    """Test construct_safe_save_path with base path > 250 chars."""
    long_base = "/" + "a" * 255
    # Calculated limit = 260 - 10 - 255 = -5.
    # This should raise ValueError because it's less than MIN_FILENAME_LENGTH (5).
    with pytest.raises(ValueError, match="SAVE_PATH_BASE is too deep"):
        construct_safe_save_path(long_base, "Any Title")


def test_send_invalid_link_type(client: FlaskClient) -> None:
    """Test send endpoint with a non-string link to ensure type safety."""
    # Sending an integer as link should trigger the type check error
    response = client.post("/send", json={"link": 12345, "title": "Some Book"})
    assert response.status_code == 400
    assert response.json is not None
    assert "Invalid request: Link must be a string" in response.json["message"]
