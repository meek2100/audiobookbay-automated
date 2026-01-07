# File: audiobook_automated/clients/manager.py
"""Manager for handling Torrent Client plugins."""

import importlib
import inspect
import logging
import re
from typing import Any

from flask import Flask

from .base import TorrentClientStrategy, TorrentStatus

logger = logging.getLogger(__name__)


class TorrentManager:
    """Manages the lifecycle and interaction with the active Torrent Client Strategy."""

    def __init__(self) -> None:
        self.strategy: TorrentClientStrategy | None = None
        self._app: Flask | None = None

    @property
    def client_type(self) -> str:
        """Return the name of the loaded client strategy."""
        if self.strategy:
            return self.strategy.__class__.__name__
        return "None"

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
            strategy_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, TorrentClientStrategy) and obj is not TorrentClientStrategy:
                    strategy_class = obj
                    break

            if not strategy_class:
                 strategy_class = getattr(module, class_name, None)

            if not strategy_class:
                raise ImportError(f"No valid strategy class found in {module_name}")

            # Instantiate the strategy
            # Extract configuration from app.config to pass explicitly
            host = app.config.get("DL_HOST", "localhost")
            port = app.config.get("DL_PORT")
            if port is None:
                port = getattr(strategy_class, "DEFAULT_PORT", 8080)

            try:
                port = int(port)
            except (ValueError, TypeError):
                port = 8080

            username = app.config.get("DL_USER")
            password = app.config.get("DL_PASS")
            scheme = app.config.get("DL_SCHEME", "http")
            timeout = app.config.get("DL_TIMEOUT", 30)

            self.strategy = strategy_class(
                host=host,
                port=port,
                username=username,
                password=password,
                scheme=scheme,
                timeout=timeout
            )
            logger.info("Plugin: Successfully loaded '%s'.", strategy_class.__name__)

        except (ImportError, AttributeError, TypeError) as e:
            logger.exception("Plugin: Failed to load client '%s'. Error: %s", client_name, e)
            # Leave self.strategy as None

    def verify_credentials(self) -> bool:
        """Verify that the loaded strategy can connect to the torrent client."""
        if not self.strategy:
            return False
        return self.strategy.verify_credentials()

    def add_magnet(self, magnet_link: str, save_path: str) -> None:
        """Add a magnet link to the client.

        Args:
            magnet_link: The magnet URI.
            save_path: The filesystem path to save the download.
        """
        if not self.strategy:
            logger.error("Manager: No torrent strategy loaded.")
            return

        category = "abb-automated"
        if self._app:
            category = self._app.config.get("DL_CATEGORY", "abb-automated")

        self.strategy.add_magnet(magnet_link, save_path, category)

    def get_status(self) -> list[TorrentStatus]:
        """Get the status of all torrents in the configured category.

        Returns:
            A list of TorrentStatus objects.
        """
        if not self.strategy:
            return []

        category = "abb-automated"
        if self._app:
            category = self._app.config.get("DL_CATEGORY", "abb-automated")

        return self.strategy.get_status(category)

    def remove_torrent(self, torrent_id: str, delete_data: bool = False) -> bool:
        """Remove a torrent from the client.

        Args:
            torrent_id: The ID (info hash).
            delete_data: Whether to delete the downloaded files.

        Returns:
            True if successful (or if strategy raises no error), False otherwise.
        """
        if not self.strategy:
            return False

        try:
            self.strategy.remove_torrent(torrent_id)
            return True
        except Exception as e:
            logger.error(f"Manager: Failed to remove torrent {torrent_id}: {e}")
            return False

    def close(self) -> None:
        """Close any open connections held by the strategy."""
        if self.strategy:
            self.strategy.close()

    def teardown_request(self, exception: BaseException | None = None) -> None:
        """Cleanup request-scoped resources."""
        if self.strategy and hasattr(self.strategy, "teardown"):
             self.strategy.teardown()
