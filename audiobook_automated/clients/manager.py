# File: audiobook_automated/clients/manager.py
"""Manager for handling Torrent Client plugins."""

import importlib
import inspect
import logging
import re
from typing import Any, cast

from flask import Flask

from .base import TorrentClientStrategy, TorrentStatus

logger = logging.getLogger(__name__)


class TorrentManager:
    """Manages the lifecycle and interaction with configured Torrent Client Strategies."""

    def __init__(self) -> None:
        """Initialize the manager."""
        self.strategy: TorrentClientStrategy | None = None
        self.clients: dict[str, TorrentClientStrategy] = {}
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

    def _instantiate_strategy(self, app: Flask, client_name: str) -> TorrentClientStrategy | None:
        """Instantiate a client strategy by name with app configuration.

        Args:
            app: The Flask application instance.
            client_name: The strategy module/client name.

        Returns:
            TorrentClientStrategy | None: The loaded strategy instance or None on error.
        """
        # SECURITY: Validate client_name to prevent arbitrary code execution
        # Only allow alphanumeric characters, underscores, and hyphens
        if not re.match(r"^[a-zA-Z0-9_\-]+$", client_name):
            logger.error("Security: Invalid DL_CLIENT name '%s'. Falling back to 'transmission'.", client_name)
            client_name = "transmission"

        module_name = f"audiobook_automated.clients.{client_name}"
        class_name = f"{client_name.capitalize()}Client"

        try:
            logger.info("Plugin: Loading download client '%s'...", client_name)
            module = importlib.import_module(module_name)

            # Find the strategy class in the module
            strategy_class = None
            for _, obj in inspect.getmembers(module, inspect.isclass):
                # Ensure it is a class before issubclass to satisfy MyPy/Pyright strict checks
                # pyright: ignore[reportUnnecessaryIsInstance]
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
            port: Any = app.config.get("DL_PORT")
            if port is None:
                port = getattr(strategy_class, "DEFAULT_PORT", 8080)

            try:
                # Handle potential string or int input
                if isinstance(port, str):
                    port_int = int(float(port))
                else:
                    port_int = int(port)
            except (ValueError, TypeError):
                port_int = 8080

            username = app.config.get("DL_USERNAME") or app.config.get("DL_USER")
            password = app.config.get("DL_PASSWORD") or app.config.get("DL_PASS")
            api_key = app.config.get("DL_API_KEY") or app.config.get("DL_KEY")
            scheme = app.config.get("DL_SCHEME", "http")
            timeout = app.config.get("CLIENT_TIMEOUT") or app.config.get("DL_TIMEOUT", 30)

            # Explicitly typecast check (though logic ensures it is a class)
            strategy_cls = cast(type[TorrentClientStrategy], strategy_class)  # type: ignore[redundant-cast]

            token = app.config.get("PUTIO_TOKEN")
            folder_id = app.config.get("PUTIO_FOLDER_ID", "0")

            instance = strategy_cls(
                host=host,
                port=port_int,
                username=username,
                password=password,
                scheme=scheme,
                timeout=timeout,
                token=token,
                folder_id=folder_id,
                api_key=api_key,
            )
            logger.info("Plugin: Successfully loaded '%s'.", client_name)
            return instance

        except (ImportError, AttributeError, TypeError) as e:
            logger.exception("Plugin: Failed to load client '%s'. Error: %s", client_name, e)
            return None

    def _load_strategy(self, app: Flask) -> None:
        """Dynamically load the configured torrent client strategy / strategies.

        Supports single client via DL_CLIENT or multiple clients via DL_CLIENTS (comma-separated).

        Args:
            app: The Flask application instance containing configuration.
        """
        self.clients.clear()
        primary_client = app.config.get("DL_CLIENT", "transmission")
        additional_clients_str = app.config.get("DL_CLIENTS", "")

        client_names: list[str] = []
        if additional_clients_str:
            client_names = [c.strip() for c in additional_clients_str.split(",") if c.strip()]
        if primary_client and primary_client not in client_names:
            client_names.insert(0, primary_client)

        for name in client_names:
            instance = self._instantiate_strategy(app, name)
            if instance:
                self.clients[name.lower()] = instance

        # Set default primary strategy
        if primary_client.lower() in self.clients:
            self.strategy = self.clients[primary_client.lower()]
        elif self.clients:
            self.strategy = next(iter(self.clients.values()))
        else:
            self.strategy = None

    def get_client(self, client_name: str | None = None) -> TorrentClientStrategy | None:
        """Get a specific strategy by name, or the default primary strategy."""
        if client_name and client_name.lower() in self.clients:
            return self.clients[client_name.lower()]
        return self.strategy

    def list_clients(self) -> list[str]:
        """Return list of configured client identifiers."""
        return list(self.clients.keys())

    def verify_credentials(self, client_name: str | None = None) -> bool:
        """Verify that the target or primary strategy can connect to the torrent client."""
        target = self.get_client(client_name)
        if not target:
            return False
        return target.verify_credentials()

    def add_magnet(self, magnet_link: str, save_path: str, client_name: str | None = None) -> None:
        """Add a magnet link to the client.

        Args:
            magnet_link: The magnet URI.
            save_path: The filesystem path to save the download.
            client_name: Optional target client strategy identifier.
        """
        target = self.get_client(client_name)
        if not target:
            logger.error("Manager: No torrent strategy loaded.")
            return

        category = "abb-automated"
        if self._app:
            category = self._app.config.get("DL_CATEGORY", "abb-automated")

        target.add_magnet(magnet_link, save_path, category)

    def get_status(self, client_name: str | None = None) -> list[TorrentStatus]:
        """Get the status of torrents in the configured category across all or targeted clients.

        Args:
            client_name: Optional client identifier to restrict query to.

        Returns:
            A list of TorrentStatus objects with client field populated.
        """
        category = "abb-automated"
        if self._app:
            category = self._app.config.get("DL_CATEGORY", "abb-automated")

        if client_name and client_name.lower() in self.clients:
            strategy_instance = self.clients[client_name.lower()]
            statuses = strategy_instance.get_status(category)
            for s in statuses:
                s.client = client_name.lower()
            return statuses

        # Multi-client status aggregation
        if len(self.clients) > 1:
            aggregated: list[TorrentStatus] = []
            for name, strategy_instance in self.clients.items():
                try:
                    statuses = strategy_instance.get_status(category)
                    for s in statuses:
                        if hasattr(s, "client"):
                            s.client = name
                    aggregated.extend(statuses)
                except Exception as e:
                    logger.warning(f"Manager: Failed to get status for client '{name}': {e}")
            return aggregated

        if not self.strategy:
            return []

        statuses = self.strategy.get_status(category)
        default_name = next(iter(self.clients.keys()), "").lower()
        if not default_name:
            default_name = self.client_type.lower().replace("client", "").replace("strategy", "")

        for s in statuses:
            if hasattr(s, "client"):
                s.client = default_name
        return statuses

    def remove_torrent(self, torrent_id: str, delete_data: bool = False, client_name: str | None = None) -> bool:
        """Remove a torrent from the client.

        Args:
            torrent_id: The ID (info hash).
            delete_data: Whether to delete the downloaded files.
            client_name: Optional specific client to remove from.

        Returns:
            True if successful, False otherwise.
        """
        target = self.get_client(client_name)
        if target:
            try:
                target.remove_torrent(torrent_id)
                return True
            except Exception as e:
                logger.error(f"Manager: Failed to remove torrent {torrent_id}: {e}")
                return False

        # If no client specified and multiple exist, attempt removal across clients
        for name, strategy_instance in self.clients.items():
            try:
                strategy_instance.remove_torrent(torrent_id)
                return True
            except Exception as e:
                logger.debug(f"Manager: Client '{name}' could not remove torrent {torrent_id}: {e}")

        return False

    def close(self) -> None:
        """Close any open connections held by all strategies."""
        for strategy_instance in self.clients.values():
            strategy_instance.close()
        if self.strategy and not self.clients:
            self.strategy.close()

    def teardown_request(self, exception: BaseException | None = None) -> None:
        """Cleanup request-scoped resources across strategies."""
        for strategy_instance in self.clients.values():
            strategy_instance.teardown()
        if self.strategy and not self.clients:
            self.strategy.teardown()
