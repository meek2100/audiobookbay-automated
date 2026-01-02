# File: tests/functional/conftest.py
"""Fixtures specific to Functional (Integration) tests."""

from collections.abc import Generator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_functional_dependencies() -> Generator[None]:
    """Mock external dependencies for all functional tests.

    Functional tests exercise the full application stack (via test_client),
    so they trigger logic that attempts real network connections (e.g. adding torrents,
    getting status). We must mock these out globally for this scope to prevent errors.

    This is scoped to functional tests only, so Unit tests in tests/unit/ can still
    test the real TorrentManager class logic.
    """
    with (
        patch("audiobook_automated.clients.manager.TorrentManager.verify_credentials", return_value=True),
        patch("audiobook_automated.clients.manager.TorrentManager.add_magnet") as mock_add,
        patch("audiobook_automated.clients.manager.TorrentManager.get_status") as mock_status,
        patch("audiobook_automated.clients.manager.TorrentManager.remove_torrent") as mock_remove,
    ):
        mock_status.return_value = []
        mock_add.return_value = None
        mock_remove.return_value = None

        yield
