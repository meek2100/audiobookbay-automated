# File: tests/unit/test_extensions.py
"""Unit tests for the Extensions module."""

# pyright: reportPrivateUsage=false

import signal
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from audiobook_automated.extensions import ScraperExecutor, register_shutdown_handlers

# Import the module where the function to be patched lives
from audiobook_automated.scraper import network as network_module


class TestExtensions(unittest.TestCase):
    """Test suite for extensions module."""

    def test_scraper_executor_lifecycle(self) -> None:
        """Test ScraperExecutor init and shutdown."""
        executor = ScraperExecutor()
        app = MagicMock(spec=Flask)
        app.config = {"SCRAPER_THREADS": 2}

        # Test submit before init raises
        with self.assertRaises(RuntimeError):
            executor.submit(print, "fail")

        executor.init_app(app)
        self.assertIsNotNone(executor._executor)

        # Test submit works
        def task(x: int) -> int:
            return x * 2

        future = executor.submit(task, 10)
        self.assertEqual(future.result(), 20)

        executor.shutdown()
        # Verify executor is present (shutdown doesn't delete it, just closes it)
        self.assertIsNotNone(executor._executor)

    @patch("signal.signal")
    def test_register_shutdown_handlers(self, mock_signal: MagicMock) -> None:
        """Test that SIGINT and SIGTERM handlers are registered."""
        app = MagicMock(spec=Flask)

        # Patch the network shutdown function using patch.object on the imported module
        # This is more robust than string patching if the module is already loaded
        with patch.object(network_module, "shutdown_network") as mock_network_shutdown:
            register_shutdown_handlers(app)

            # Check that signal.signal was called exactly twice
            self.assertEqual(mock_signal.call_count, 2)

            # Verify specific signals were registered
            registered_signals = [call[0][0] for call in mock_signal.call_args_list]
            self.assertIn(signal.SIGTERM, registered_signals)
            self.assertIn(signal.SIGINT, registered_signals)

            # Extract handler and verify its logic
            handler = mock_signal.call_args_list[0][0][1]
            self.assertTrue(callable(handler))

            with patch("audiobook_automated.extensions.executor.shutdown") as mock_shutdown:
                with patch("sys.exit") as mock_exit:
                    handler(signal.SIGTERM, None)

                    mock_shutdown.assert_called_with(wait=False)
                    mock_network_shutdown.assert_called_once()
                    mock_exit.assert_called_with(0)
