"""Module handling torrent client interactions using the Strategy pattern."""

import logging
import threading
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Literal, Protocol, TypedDict, cast
from urllib.parse import urlparse

from deluge_web_client import DelugeWebClient
from flask import Flask
from qbittorrentapi import Client as QbClient
from transmission_rpc import Client as TxClient

logger = logging.getLogger(__name__)


class TorrentClientType(StrEnum):
    """Enumeration of supported torrent clients."""

    QBITTORRENT = "qbittorrent"
    TRANSMISSION = "transmission"
    DELUGE = "deluge"


class TorrentStatus(TypedDict):
    """TypedDict representing a standardized torrent status object."""

    id: str | int
    name: str
    progress: float
    state: str
    size: str


class QbTorrentProtocol(Protocol):
    """Protocol defining the expected structure of a qBittorrent torrent object."""

    hash: str
    name: str
    state: str
    total_size: int
    progress: float


class TorrentClientStrategy(ABC):
    """Abstract base class for torrent client strategies."""

    def __init__(self, host: str, port: int, username: str | None, password: str | None, scheme: str = "http") -> None:
        """Initialize the client strategy configuration."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.scheme = scheme

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the torrent client."""
        pass  # pragma: no cover

    @abstractmethod
    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        """Add a magnet link to the client."""
        pass  # pragma: no cover

    @abstractmethod
    def remove_torrent(self, torrent_id: str) -> None:
        """Remove a torrent by ID."""
        pass  # pragma: no cover

    @abstractmethod
    def get_status(self, category: str) -> list[TorrentStatus]:
        """Retrieve status of torrents in the given category."""
        pass  # pragma: no cover

    @staticmethod
    def _format_size(size_bytes: int | float | str | None) -> str:
        """Format bytes into human-readable B, KB, MB, GB, TB, PB."""
        if size_bytes is None:
            return "Unknown"
        try:
            size: float = float(size_bytes)
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if size < 1024.0:
                    return f"{size:.2f} {unit}"
                size /= 1024.0
            return f"{size:.2f} PB"
        except (ValueError, TypeError):
            return "Unknown"


class QbittorrentStrategy(TorrentClientStrategy):
    """Strategy implementation for qBittorrent."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.client: QbClient | None = None

    def connect(self) -> None:
        self.client = QbClient(
            host=self.host,
            port=self.port,
            username=self.username or "",
            password=self.password or "",
            REQUESTS_ARGS={"timeout": 30},
        )
        self.client.auth_log_in()

    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        if not self.client:
            raise ConnectionError("qBittorrent client not connected")
        result = self.client.torrents_add(urls=magnet_link, save_path=save_path, category=category)
        if isinstance(result, str) and result.lower() != "ok.":
            logger.warning(f"qBittorrent add returned unexpected response: {result}")

    def remove_torrent(self, torrent_id: str) -> None:
        if not self.client:
            raise ConnectionError("qBittorrent client not connected")
        self.client.torrents_delete(torrent_hashes=torrent_id, delete_files=False)

    def get_status(self, category: str) -> list[TorrentStatus]:
        if not self.client:
            raise ConnectionError("qBittorrent client not connected")
        results: list[TorrentStatus] = []
        qb_torrents = cast(list[QbTorrentProtocol], self.client.torrents_info(category=category))
        for qb_torrent in qb_torrents:
            results.append(
                {
                    "id": qb_torrent.hash,
                    "name": qb_torrent.name,
                    "progress": round(qb_torrent.progress * 100, 2) if qb_torrent.progress else 0.0,
                    "state": qb_torrent.state,
                    "size": self._format_size(qb_torrent.total_size),
                }
            )
        return results


class TransmissionStrategy(TorrentClientStrategy):
    """Strategy implementation for Transmission."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.client: TxClient | None = None

    def connect(self) -> None:
        safe_scheme = cast(Literal["http", "https"], self.scheme)
        self.client = TxClient(
            host=self.host,
            port=self.port,
            protocol=safe_scheme,
            username=self.username,
            password=self.password,
            timeout=30,
        )

    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        if not self.client:
            raise ConnectionError("Transmission client not connected")
        try:
            self.client.add_torrent(magnet_link, download_dir=save_path, labels=[category])
        except Exception as e:
            logger.warning(f"Transmission label assignment failed: {e}. Retrying without labels.")
            self.client.add_torrent(magnet_link, download_dir=save_path)

    def remove_torrent(self, torrent_id: str) -> None:
        if not self.client:
            raise ConnectionError("Transmission client not connected")
        tid: int | str
        try:
            tid = int(torrent_id)
        except ValueError:
            tid = torrent_id
            logger.debug(f"Transmission: ID {torrent_id} is not an integer, using as string hash.")
        self.client.remove_torrent(ids=[tid], delete_data=False)

    def get_status(self, category: str) -> list[TorrentStatus]:
        if not self.client:
            raise ConnectionError("Transmission client not connected")
        results: list[TorrentStatus] = []
        tx_torrents = self.client.get_torrents()
        for tx_torrent in tx_torrents:
            results.append(
                {
                    "id": str(tx_torrent.id),
                    "name": tx_torrent.name,
                    "progress": round(tx_torrent.progress * 100, 2) if tx_torrent.progress else 0.0,
                    "state": tx_torrent.status.name,
                    "size": self._format_size(tx_torrent.total_size),
                }
            )
        return results


class DelugeStrategy(TorrentClientStrategy):
    """Strategy implementation for Deluge."""

    def __init__(self, dl_url: str | None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.dl_url = dl_url
        self.client: DelugeWebClient | None = None

    def connect(self) -> None:
        # DelugeWebClient uses the full URL
        url = self.dl_url or f"{self.scheme}://{self.host}:{self.port}"
        self.client = DelugeWebClient(url=url, password=self.password or "")
        self.client.login()

    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        if not self.client:
            raise ConnectionError("Deluge client not connected")
        try:
            self.client.add_torrent_magnet(magnet_link, save_directory=save_path, label=category)
        except Exception as e:
            error_msg = str(e).lower()
            if "label" in error_msg or "unknown parameter" in error_msg:
                logger.warning(
                    f"Deluge Plugin Error ({e}). Adding torrent without category (Label plugin likely disabled)."
                )
                try:
                    self.client.add_torrent_magnet(magnet_link, save_directory=save_path)
                except Exception as e2:
                    logger.error(f"Deluge fallback failed: {e2}", exc_info=True)
                    raise e2
            else:
                raise e

    def remove_torrent(self, torrent_id: str) -> None:
        if not self.client:
            raise ConnectionError("Deluge client not connected")
        self.client.remove_torrent(torrent_id, remove_data=False)

    def get_status(self, category: str) -> list[TorrentStatus]:
        if not self.client:
            raise ConnectionError("Deluge client not connected")
        results: list[TorrentStatus] = []
        deluge_torrents = self.client.get_torrents_status(
            filter_dict={"label": category},
            keys=["name", "state", "progress", "total_size"],
        )

        if deluge_torrents.result is not None:
            if isinstance(deluge_torrents.result, dict):
                results_dict = deluge_torrents.result
                for key, deluge_data in results_dict.items():
                    if not isinstance(deluge_data, dict):
                        continue
                    progress_val = deluge_data.get("progress")
                    try:
                        progress = round(float(progress_val), 2) if progress_val is not None else 0.0
                    except (ValueError, TypeError):
                        progress = 0.0

                    results.append(
                        {
                            "id": key,
                            "name": deluge_data.get("name", "Unknown"),
                            "progress": progress,
                            "state": deluge_data.get("state", "Unknown"),
                            "size": self._format_size(deluge_data.get("total_size")),
                        }
                    )
            else:
                logger.warning(f"Deluge returned unexpected data type: {type(deluge_torrents.result)}")
        else:
            logger.warning("Deluge returned empty or invalid result payload.")
        return results


class TorrentManager:
    """
    Manages interactions with various torrent clients using the Strategy pattern.
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
        self._local = threading.local()

    def init_app(self, app: Flask) -> None:
        """Initialize the TorrentManager with configuration from the Flask app."""
        config = app.config
        self.client_type = config.get("DL_CLIENT")

        raw_host = config.get("DL_HOST")
        raw_port = config.get("DL_PORT")

        self.host = raw_host or "localhost"
        self.port = int(raw_port or 8080)
        self.username = config.get("DL_USERNAME")
        self.password = config.get("DL_PASSWORD")
        self.category = config.get("DL_CATEGORY", "abb-automated")
        self.scheme = config.get("DL_SCHEME", "http")
        self.dl_url = config.get("DL_URL")

        # URL Parsing / Default Logic
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

        if not self.dl_url:
            # Case 1: Host provided, Port missing
            if raw_host and not raw_port:
                if self.client_type == TorrentClientType.DELUGE:
                    self.port = 8112
                else:
                    self.port = 8080
                logger.info(f"DL_PORT missing. Defaulting to {self.port} for {self.client_type}.")
                self.dl_url = f"{self.scheme}://{self.host}:{self.port}"

            # Case 2: Host missing (implies using localhost default)
            elif not raw_host:
                if self.client_type == TorrentClientType.DELUGE:
                    logger.warning("DL_HOST missing. Defaulting Deluge URL to localhost:8112.")
                    self.host = "localhost"
                    self.port = 8112
                    self.dl_url = "http://localhost:8112"
                else:
                    # Default for others
                    self.dl_url = f"{self.scheme}://{self.host}:{self.port}"

            # Case 3: Both provided or fallback handled
            else:
                self.dl_url = f"{self.scheme}://{self.host}:{self.port}"

        # Reset thread local
        self._local = threading.local()

    def _get_strategy(self) -> TorrentClientStrategy | None:
        """Return the thread-local strategy instance or create/connect if needed."""
        if hasattr(self._local, "strategy") and self._local.strategy:
            return cast(TorrentClientStrategy | None, self._local.strategy)

        logger.debug(f"Initializing new {self.client_type} strategy for thread {threading.get_ident()}...")

        strategy: TorrentClientStrategy | None = None

        try:
            if self.client_type == TorrentClientType.QBITTORRENT:
                strategy = QbittorrentStrategy(self.host, self.port, self.username, self.password, self.scheme)
            elif self.client_type == TorrentClientType.TRANSMISSION:
                strategy = TransmissionStrategy(self.host, self.port, self.username, self.password, self.scheme)
            elif self.client_type == TorrentClientType.DELUGE:
                strategy = DelugeStrategy(self.dl_url, self.host, self.port, self.username, self.password, self.scheme)
            else:
                raise ValueError(f"Unsupported download client configured: {self.client_type}")

            strategy.connect()
            self._local.strategy = strategy

        except Exception as e:
            logger.error(f"Error initializing torrent client strategy: {e}", exc_info=True)
            self._local.strategy = None

        return getattr(self._local, "strategy", None)

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
            self._local.strategy = None
            self._add_magnet_logic(magnet_link, save_path)

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
            self._local.strategy = None
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
            self._local.strategy = None
            return self._get_status_logic()

    def _get_status_logic(self) -> list[TorrentStatus]:
        strategy = self._get_strategy()
        if not strategy:
            raise ConnectionError("Torrent client is not connected.")
        return strategy.get_status(self.category)
