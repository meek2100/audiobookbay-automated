# File: tests/functional/test_routes_extra.py
"""Tests for edge cases in routes."""

from unittest.mock import patch

from flask import Flask
from flask.testing import FlaskClient


def test_delete_torrent_not_found(client: FlaskClient, app: Flask) -> None:
    """Test that deleting a non-existent torrent returns 404."""
    with patch("audiobook_automated.routes.torrent_manager.get_status", return_value=[]):
        # We need to simulate the torrent check failure
        response = client.post("/delete", json={"id": "nonexistent"})
        assert response.status_code == 404
        json_data = response.json
        assert json_data is not None
        assert json_data["message"] == "Torrent not found"
