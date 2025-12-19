# File: tests/unit/clients/test_manager_syntax.py
"""Unit tests for Manager SyntaxError handling."""

import importlib
from unittest.mock import MagicMock, patch

from audiobook_automated.clients.manager import TorrentManager


class TestManagerSyntax:
    """Test suite for Manager SyntaxError handling."""

    def test_syntax_error_in_plugin(self, app):
        """Test that a SyntaxError in the plugin module is caught and logged."""
        manager = TorrentManager()
        app.config["DL_CLIENT"] = "test_client"

        # We need to initialize the app so manager picks up the config
        manager.init_app(app)

        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = SyntaxError("Test Syntax Error")

            strategy = manager._get_strategy()

            assert strategy is None
            mock_import.assert_called()
