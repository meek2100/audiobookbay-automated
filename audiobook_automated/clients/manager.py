"""TorrentManager implementation using dynamic strategy loading."""

import importlib
import logging
import threading
from typing import cast
from urllib.parse import urlparse

from flask import Flask

from .base import TorrentClientStrategy, TorrentStatus

logger = logging.getLogger(__name__)


class ClientLocal(threading.local):
    """Thread-local storage for client strategies with strict typing."""

    def __init__(self) -> None:
        """Initialize thread-local attributes."""
        super().__init__()
        self.strategy: TorrentClientStrategy | None = None


class TorrentManager:
    """Manages interactions with various torrent clients using the Strategy pattern."""

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

        self.username = config.get("DL_USERNAME")
        self.password = config.get("DL_PASSWORD")
        self.category = config.get("DL_CATEGORY", "abb-automated")
        self.scheme = config.get("DL_SCHEME", "http")
        self.dl_url = config.get("DL_URL")

        # 1. Attempt to load the strategy class FIRST to get its defaults
        # We catch basic ImportErrors here to avoid crashing init, but full validation happens in _get_strategy
        default_port = 8080
        if self.client_type:
            try:
                # We use a temporary loader just to peek at DEFAULT_PORT
                # Pass explicit 'None' logging to suppress errors during this speculative check
                temp_class = self._load_strategy_class(self.client_type, suppress_errors=True)
                if temp_class:
                    default_port = temp_class.DEFAULT_PORT
            except Exception as e:
                # S110: Log exception instead of pass
                # Ignore errors during init; they will be caught/logged when connection is attempted
                logger.debug(f"Error checking default port for {self.client_type}: {e}")

        # URL Parsing with dynamic default port
        if self.dl_url:
            try:
                parsed = urlparse(self.dl_url)
                self.host = parsed.hostname or raw_host or "localhost"
                self.port = parsed.port or int(raw_port or default_port)
                if parsed.scheme:
                    self.scheme = parsed.scheme
            except Exception as e:
                logger.warning(f"Failed to parse DL_URL: {e}. Using raw config values.")
                self.host = raw_host or "localhost"
                self.port = int(raw_port or default_port)
        else:
            self.host = raw_host or "localhost"
            self.port = int(raw_port or default_port)
            self.dl_url = f"{self.scheme}://{self.host}:{self.port}"

            # Host default warning for Deluge (Legacy check, can be kept or eventually moved to plugin)
            if not raw_host and self.client_type == "deluge":
                logger.warning("DL_HOST missing. Defaulting Deluge to localhost.")

        # Reset thread local
        self._local = ClientLocal()

    def _load_strategy_class(
        self, client_name: str | None, suppress_errors: bool = False
    ) -> type[TorrentClientStrategy] | None:
        """Dynamically load the strategy class for the given client name."""
        if not client_name:
            return None

        try:
            # Load from internal package
            module = importlib.import_module(f".{client_name}", package="audiobook_automated.clients")
            if hasattr(module, "Strategy") and issubclass(module.Strategy, TorrentClientStrategy):
                # FIX: Explicit cast to satisfy MyPy no-any-return check
                return cast(type[TorrentClientStrategy], module.Strategy)
            elif not suppress_errors:
                logger.error(f"Client plugin '{client_name}' found, but it does not export a 'Strategy' class.")
        except (ImportError, ModuleNotFoundError):
            if not suppress_errors:
                # Pass silently during config/init phase; detailed errors happen in _get_strategy
                pass
        return None

    def _get_strategy(self) -> TorrentClientStrategy | None:
        """Return the thread-local strategy instance or create/connect if needed."""
        if self._local.strategy:
            return self._local.strategy

        if not self.client_type:
            logger.error("DL_CLIENT not configured.")
            return None

        try:
            # Load class (cached by Python's import system)
            # MOVED INSIDE TRY BLOCK: Captures SyntaxError, ImportError, and other load-time failures safely.
            strategy_class = self._load_strategy_class(self.client_type)

            if not strategy_class:
                logger.error(f"Could not load strategy for client: {self.client_type}")
                return None

            strategy = strategy_class(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                scheme=self.scheme,
                dl_url=self.dl_url,
            )
            strategy.connect()
            self._local.strategy = strategy
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
