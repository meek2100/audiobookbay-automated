# File: audiobook_automated/clients/manager.py
"""TorrentManager implementation using dynamic strategy loading."""

import importlib
import logging
import re
import threading
from typing import Any, TypeIs
from urllib.parse import urlparse

from flask import Flask

from .base import TorrentClientStrategy, TorrentStatus

logger = logging.getLogger(__name__)


class ClientLocal(threading.local):
    """Thread-local storage for client strategies with strict typing."""

    def __init__(self) -> None:
        """Initialize thread-local attributes.

        Sets the strategy attribute to None initially.
        """
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
        self.client_timeout: int = 30

        # Thread-local storage for client instances
        self._local = ClientLocal()

    def init_app(self, app: Flask) -> None:
        """Initialize the TorrentManager with configuration from the Flask app."""
        config = app.config
        self.client_timeout = config.get("CLIENT_TIMEOUT", 30)

        dl_client = config.get("DL_CLIENT")

        if dl_client:
            # SAFETY: Validate client name to prevent directory traversal or injection
            if not re.match(r"^[a-zA-Z0-9_]+$", dl_client):
                raise RuntimeError(  # pragma: no cover
                    f"Invalid DL_CLIENT value: '{dl_client}'. Must contain only alphanumeric characters and underscores."
                )
            self.client_type = dl_client.lower()
        else:
            self.client_type = None

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

    def _is_strategy(self, cls: Any) -> TypeIs[type[TorrentClientStrategy]]:
        """Check if a class is a valid TorrentClientStrategy subclass using TypeGuard."""
        return isinstance(cls, type) and issubclass(cls, TorrentClientStrategy)

    def _load_strategy_class(
        self, client_name: str | None, suppress_errors: bool = False
    ) -> type[TorrentClientStrategy] | None:
        """Dynamically load the strategy class for the given client name.

        Distinguishes between a missing plugin module (acceptable) and a missing dependency
        WITHIN that plugin (critical error).
        """
        if not client_name:
            return None

        # SECURITY: Prevent importing arbitrary standard library modules by enforcing package path
        # This ensures DL_CLIENT="json" or DL_CLIENT="os" fails unless they exist as plugins
        package_name = __package__ or "audiobook_automated.clients"
        full_module_name = f"{package_name}.{client_name}"

        try:
            # Load from internal package
            module = importlib.import_module(f".{client_name}", package=package_name)
            strategy_class = getattr(module, "Strategy", None)

            if self._is_strategy(strategy_class):
                # FIX: Assign to explicitly typed variable to satisfy both Mypy (no-any-return)
                # and Pyright (redundant-cast). Mypy allows Any->Typed assignment; Pyright allows Typed->Typed.
                validated_class: type[TorrentClientStrategy] = strategy_class
                return validated_class
            elif not suppress_errors:  # pragma: no cover
                logger.error(f"Client plugin '{client_name}' found, but it does not export a 'Strategy' class.")

        except ModuleNotFoundError as e:
            # CRITICAL FIX: Distinguish between the plugin itself being missing vs. a dependency inside it.
            if e.name == full_module_name:
                if not suppress_errors:
                    logger.error(f"Client plugin '{client_name}' not found.")
            else:
                # This is a missing dependency inside the plugin (e.g. user forgot pip install transmission-rpc)
                raise e

        except ImportError as e:
            # Handle other import errors (e.g. circular imports)
            if not suppress_errors:  # pragma: no cover
                logger.error(f"Error importing client plugin '{client_name}': {e}")

        return None

    def _get_strategy(self) -> TorrentClientStrategy | None:
        """Return the thread-local strategy instance or create/connect if needed."""
        if self._local.strategy:
            return self._local.strategy

        if not self.client_type:  # pragma: no cover
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
                timeout=self.client_timeout,
            )
            strategy.connect()
            self._local.strategy = strategy
        except SyntaxError:  # pragma: no cover
            logger.critical(f"Syntax Error in client plugin: {self.client_type}", exc_info=True)
            self._local.strategy = None
        except Exception as e:  # pragma: no cover
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
            except Exception as e:  # pragma: no cover
                logger.warning(f"Error closing strategy during reconnect: {e}")
        self._local.strategy = None

    def _add_magnet_logic(self, magnet_link: str, save_path: str) -> None:
        """Add a magnet link via the active strategy.

        Args:
            magnet_link: The magnet URI.
            save_path: The filesystem path.

        Raises:
            ConnectionError: If client is not connected.
        """
        strategy = self._get_strategy()
        if not strategy:
            raise ConnectionError("Torrent client is not connected.")
        logger.info(f"Adding torrent to {self.client_type} at {save_path}")
        strategy.add_magnet(magnet_link, save_path, self.category)

    def remove_torrent(self, torrent_id: str) -> None:
        """Remove a torrent by ID."""
        try:
            self._remove_torrent_logic(torrent_id)
        except Exception as e:  # pragma: no cover
            logger.warning(f"Failed to remove torrent ({e}). Attempting to reconnect...", exc_info=True)
            self._force_disconnect()
            self._remove_torrent_logic(torrent_id)

    def _remove_torrent_logic(self, torrent_id: str) -> None:
        """Remove a torrent via the active strategy.

        Args:
            torrent_id: The torrent info hash or ID.

        Raises:
            ConnectionError: If client is not connected.
        """
        strategy = self._get_strategy()
        if not strategy:
            raise ConnectionError("Torrent client is not connected.")
        logger.info(f"Removing torrent {torrent_id} from {self.client_type}")
        strategy.remove_torrent(torrent_id)

    def get_status(self) -> list[TorrentStatus]:
        """Retrieve the status of current downloads."""
        try:
            return self._get_status_logic()
        except Exception as e:  # pragma: no cover
            logger.warning(f"Failed to get status ({e}). Reconnecting...", exc_info=True)
            self._force_disconnect()
            return self._get_status_logic()

    def _get_status_logic(self) -> list[TorrentStatus]:
        """Retrieve torrent status via the active strategy.

        Returns:
            list[TorrentStatus]: List of torrent status objects.

        Raises:
            ConnectionError: If client is not connected.
        """
        strategy = self._get_strategy()
        if not strategy:
            raise ConnectionError("Torrent client is not connected.")
        return strategy.get_status(self.category)

    def teardown_request(self, exception: BaseException | None = None) -> None:
        """Close thread-local resources at the end of a request.

        Args:
            exception: The exception that caused the request to fail, if any.
        """
        if self._local.strategy:
            try:
                # EAFP: Strategy might not have close method or might fail
                if hasattr(self._local.strategy, "close"):
                    self._local.strategy.close()
            except Exception as e:  # pragma: no cover
                logger.warning(f"Error closing strategy during teardown: {e}")
            finally:
                self._local.strategy = None
