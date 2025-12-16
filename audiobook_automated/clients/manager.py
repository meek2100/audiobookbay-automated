# audiobook_automated/clients/manager.py
"""TorrentManager implementation using dynamic strategy loading."""

import importlib
import logging
import threading
from urllib.parse import urlparse

from flask import Flask

from .base import TorrentClientStrategy, TorrentStatus

logger = logging.getLogger(__name__)


class ClientLocal(threading.local):
    """Thread-local storage for client strategies with strict typing.

    Ensures that attributes are initialized for every new thread context.
    """

    def __init__(self) -> None:
        """Initialize thread-local attributes."""
        super().__init__()
        self.strategy: TorrentClientStrategy | None = None


class TorrentManager:
    """Manages interactions with various torrent clients using the Strategy pattern.

    Uses thread-local storage to ensure thread safety for the underlying sessions.
    """

    def __init__(self) -> None:
        """Initialize the TorrentManager state."""
        self.client_type: str | None = None
        self.host: str = "localhost"
        self.port: int = 8080
        self.username: str | None = None
        self.password: str | None = None
        self.category: str = "abb-automated"
        self.scheme: str = "http"
        self.dl_url: str | None = None

        # Thread-local storage for client instances
        self._local = ClientLocal()

    def init_app(self, app: Flask) -> None:
        """Initialize the TorrentManager with configuration from the Flask app."""
        config = app.config

        dl_client = config.get("DL_CLIENT")
        # Normalize to lowercase to match module filenames
        self.client_type = dl_client.lower() if dl_client else None

        raw_host = config.get("DL_HOST")
        raw_port = config.get("DL_PORT")

        self.host = raw_host or "localhost"
        self.port = int(raw_port or 8080)
        self.username = config.get("DL_USERNAME")
        self.password = config.get("DL_PASSWORD")
        self.category = config.get("DL_CATEGORY", "abb-automated")
        self.scheme = config.get("DL_SCHEME", "http")
        self.dl_url = config.get("DL_URL")

        # URL Parsing
        if self.dl_url:
            try:
                parsed = urlparse(self.dl_url)
                if parsed.hostname:
                    self.host = parsed.hostname
                if parsed.port:
                    self.port = parsed.port
                if parsed.scheme:
                    self.scheme = parsed.scheme
            except Exception as e:
                logger.warning(f"Failed to parse DL_URL: {e}. Using raw config values.")

        self._configure_defaults(raw_host, raw_port)

        # Reset thread local
        self._local = ClientLocal()

    def _configure_defaults(self, raw_host: str | None, raw_port: str | None) -> None:
        """Configure default ports and URLs based on client type."""
        # If DL_URL is explicitly set, we do not need to construct it or guess ports
        if self.dl_url:
            return

        # Legacy Default Handling:
        # Deluge defaults to port 8112 if the user did NOT explicitly provide a port.
        # Note: 'self.port' is already set to 8080 by default in init_app if raw_port is None.
        if not raw_port and self.client_type == "deluge":
            self.port = 8112
            logger.info("DL_PORT missing. Defaulting to 8112 for Deluge.")
        elif not raw_port:
            logger.info(f"DL_PORT missing. Defaulting to {self.port} for {self.client_type}.")

        # Handle host default warning (init_app already sets self.host="localhost")
        if not raw_host and self.client_type == "deluge":
            logger.warning("DL_HOST missing. Defaulting Deluge to localhost.")

        # Construct final URL from normalized values
        self.dl_url = f"{self.scheme}://{self.host}:{self.port}"

    def _get_strategy(self) -> TorrentClientStrategy | None:
        """Return the thread-local strategy instance or create/connect if needed."""
        if self._local.strategy:
            return self._local.strategy

        if not self.client_type:
            # Should be caught by init check but robust just in case
            logger.error("DL_CLIENT not configured.")
            return None  # pragma: no cover

        logger.debug(f"Initializing new {self.client_type} strategy for thread {threading.get_ident()}...")

        strategy: TorrentClientStrategy | None = None

        try:
            # Dynamic Loading
            # This relies on the file audiobook_automated/clients/{self.client_type}.py existing
            module = importlib.import_module(f".{self.client_type}", package="audiobook_automated.clients")

            # Validate that the module actually has the Strategy class
            # Cast to Any to satisfy MyPy since it doesn't know the module content
            if not hasattr(module, "Strategy"):
                logger.error(f"Client plugin '{self.client_type}' found, but it does not export a 'Strategy' class.")
                return None

            # Expecting a class named 'Strategy'
            strategy_class = module.Strategy

            # Instantiate with standard args + kwargs for flexibility
            strategy = strategy_class(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                scheme=self.scheme,
                dl_url=self.dl_url,
            )

            if strategy:
                strategy.connect()
                self._local.strategy = strategy

        except (ImportError, ModuleNotFoundError):
            logger.error(f"Unsupported download client configured or missing plugin: {self.client_type}", exc_info=True)
            self._local.strategy = None
        except SyntaxError:
            logger.critical(f"Syntax Error in client plugin: {self.client_type}", exc_info=True)
            self._local.strategy = None
        except Exception as e:
            logger.error(f"Error initializing torrent client strategy: {e}", exc_info=True)
            self._local.strategy = None

        return self._local.strategy

    def verify_credentials(self) -> bool:
        """Verify if the client can connect."""
        if self._get_strategy():
            logger.info(f"Successfully connected to {self.client_type}")
            return True
        logger.warning(f"Could not connect to {self.client_type} at startup.")
        return False

    def add_magnet(self, magnet_link: str, save_path: str) -> None:
        """Add a magnet link to the configured torrent client."""
        try:
            self._add_magnet_logic(magnet_link, save_path)
        except Exception as e:
            logger.warning(f"Failed to add torrent ({e}). Attempting to reconnect...", exc_info=True)
            self._force_disconnect()
            self._add_magnet_logic(magnet_link, save_path)

    def _force_disconnect(self) -> None:
        """Close and clear the current strategy to force a fresh connection on retry."""
        if self._local.strategy:
            try:
                # EAFP: Strategy might not have close method or might fail
                if hasattr(self._local.strategy, "close"):
                    self._local.strategy.close()
            except Exception as e:
                logger.warning(f"Error closing strategy during reconnect: {e}")
        self._local.strategy = None

    def _add_magnet_logic(self, magnet_link: str, save_path: str) -> None:
        strategy = self._get_strategy()
        if not strategy:
            raise ConnectionError("Torrent client is not connected.")
        logger.info(f"Adding torrent to {self.client_type} at {save_path}")
        strategy.add_magnet(magnet_link, save_path, self.category)

    def remove_torrent(self, torrent_id: str) -> None:
        """Remove a torrent by ID."""
        try:
            self._remove_torrent_logic(torrent_id)
        except Exception as e:
            logger.warning(f"Failed to remove torrent ({e}). Attempting to reconnect...", exc_info=True)
            self._force_disconnect()
            self._remove_torrent_logic(torrent_id)

    def _remove_torrent_logic(self, torrent_id: str) -> None:
        strategy = self._get_strategy()
        if not strategy:
            raise ConnectionError("Torrent client is not connected.")
        logger.info(f"Removing torrent {torrent_id} from {self.client_type}")
        strategy.remove_torrent(torrent_id)

    def get_status(self) -> list[TorrentStatus]:
        """Retrieve the status of current downloads."""
        try:
            return self._get_status_logic()
        except Exception as e:
            logger.warning(f"Failed to get status ({e}). Reconnecting...", exc_info=True)
            self._force_disconnect()
            return self._get_status_logic()

    def _get_status_logic(self) -> list[TorrentStatus]:
        strategy = self._get_strategy()
        if not strategy:
            raise ConnectionError("Torrent client is not connected.")
        return strategy.get_status(self.category)
