# File: audiobook_automated/clients/manager.py
"""Manager for handling Torrent Client plugins."""

import importlib
import inspect
import logging
import os
import re
from typing import Any, cast

from flask import Flask

from .base import TorrentClientStrategy

logger = logging.getLogger(__name__)


class TorrentManager:
    """Manages the lifecycle and interaction with the active Torrent Client Strategy."""

    def __init__(self) -> None:
        self.strategy: TorrentClientStrategy | None = None
        self._app: Flask | None = None

    def init_app(self, app: Flask) -> None:
        """Initialize the manager with the Flask application.

        Args:
            app: The Flask application instance.
        """
        self._app = app
        self._load_strategy(app)

    def _load_strategy(self, app: Flask) -> None:
        """Dynamically load the configured torrent client strategy.

        Args:
            app: The Flask application instance containing configuration.
        """
        client_name = app.config.get("DL_CLIENT", "transmission")

        # SECURITY: Validate client_name to prevent arbitrary code execution
        # Only allow alphanumeric characters, underscores, and hyphens
        if not re.match(r"^[a-zA-Z0-9_\-]+$", client_name):
            logger.error("Security: Invalid DL_CLIENT name '%s'. Falling back to 'transmission'.", client_name)
            client_name = "transmission"

        module_name = f"audiobook_automated.clients.{client_name}"
        class_name = f"{client_name.capitalize()}Client"

        try:
            logger.info("Plugin: Loading client strategy '%s'...", client_name)
            module = importlib.import_module(module_name)

            # Find the strategy class in the module
            # We look for a class that inherits from TorrentClientStrategy
            strategy_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, TorrentClientStrategy) and obj is not TorrentClientStrategy:
                    strategy_class = obj
                    break

            if not strategy_class:
                 # Fallback: try looking for class name matching convention (e.g. TransmissionClient)
                 strategy_class = getattr(module, class_name, None)

            if not strategy_class:
                raise ImportError(f"No valid strategy class found in {module_name}")

            # Instantiate the strategy
            # Note: Strategies should accept **kwargs or config in __init__
            # For now, we assume they access current_app or are initialized later.
            # Ideally, we pass config here.

            # We pass the app config to the strategy
            self.strategy = strategy_class(app.config)
            logger.info("Plugin: Successfully loaded '%s'.", strategy_class.__name__)

        except (ImportError, AttributeError) as e:
            logger.exception("Plugin: Failed to load client '%s'. Error: %s", client_name, e)
            # Fallback to a dummy/error strategy or re-raise
            # For now, we leave self.strategy as None, which will cause errors on use.

    def verify_credentials(self) -> bool:
        """Verify that the loaded strategy can connect to the torrent client.

        Returns:
            True if connected, False otherwise.
        """
        if not self.strategy:
            return False
        return self.strategy.verify_credentials()

    def add_torrent(self, magnet_link: str, save_path: str) -> str | None:
        """Add a torrent to the client.

        Args:
            magnet_link: The magnet URI.
            save_path: The filesystem path to save the download.

        Returns:
            The info hash of the added torrent, or None if failed.
        """
        if not self.strategy:
            logger.error("Manager: No torrent strategy loaded.")
            return None
        return self.strategy.add_torrent(magnet_link, save_path)

    def get_status(self, torrent_id: str) -> Any:
        """Get the status of a specific torrent.

        Args:
            torrent_id: The ID (info hash) of the torrent.

        Returns:
            The status object/dict returned by the strategy.
        """
        if not self.strategy:
            return None
        return self.strategy.get_status(torrent_id)

    def remove_torrent(self, torrent_id: str, delete_data: bool = False) -> bool:
        """Remove a torrent from the client.

        Args:
            torrent_id: The ID (info hash).
            delete_data: Whether to delete the downloaded files.

        Returns:
            True if successful, False otherwise.
        """
        if not self.strategy:
            return False
        return self.strategy.remove_torrent(torrent_id, delete_data)

    def close(self) -> None:
        """Close any open connections held by the strategy."""
        if self.strategy:
            self.strategy.close()

    def teardown_request(self, exception: BaseException | None = None) -> None:
        """Cleanup request-scoped resources (e.g. thread-local sessions)."""
        # This is called by Flask at the end of every request.
        # We delegate to the strategy if it supports it.
        # Most strategies use a shared session or connection pool,
        # but some might use thread-locals that need clearing.
        if self.strategy and hasattr(self.strategy, "teardown"):
             self.strategy.teardown()
