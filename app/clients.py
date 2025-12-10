import logging
import threading
from enum import StrEnum
from typing import Literal, Protocol, TypedDict, cast

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


class TorrentManager:
    """
    Manages interactions with various torrent clients (qBittorrent, Transmission, Deluge).
    Uses thread-local storage to ensure thread safety for the underlying sessions.
    """

    def __init__(self) -> None:
        """Initialize the TorrentManager state."""
        self.client_type: str | None = None
        self.host: str | None = None
        self.port: str | None = None
        self.username: str | None = None
        self.password: str | None = None
        self.category: str = "abb-automated"
        self.scheme: str = "http"
        self.dl_url: str | None = None

        # Thread-local storage for client instances
        # This ensures that each thread gets its own independent connection
        self._local = threading.local()

    def init_app(self, app: Flask) -> None:
        """
        Initialize the TorrentManager with configuration from the Flask app.

        Args:
            app: The Flask application instance.
        """
        config = app.config
        self.client_type = config.get("DL_CLIENT")
        self.host = config.get("DL_HOST")
        self.port = config.get("DL_PORT")
        self.username = config.get("DL_USERNAME")
        self.password = config.get("DL_PASSWORD")
        self.category = config.get("DL_CATEGORY", "abb-automated")
        self.scheme = config.get("DL_SCHEME", "http")

        # Normalize connection URL for Deluge
        self.dl_url = config.get("DL_URL")

        if not self.dl_url:
            # Handle case where host is set but port is missing
            if self.host and not self.port:
                if self.client_type == TorrentClientType.DELUGE:
                    self.port = "8112"
                else:
                    self.port = "8080"
                logger.info(f"DL_PORT missing. Defaulting to {self.port} for {self.client_type}.")

            # Construct URL if host and port are available
            if self.host and self.port:
                self.dl_url = f"{self.scheme}://{self.host}:{self.port}"
            elif self.client_type == TorrentClientType.DELUGE:
                logger.warning("DL_HOST missing. Defaulting Deluge URL to localhost:8112.")
                self.dl_url = "http://localhost:8112"

        # RESET: Ensure clean state if re-initialized (e.g. testing)
        self._local = threading.local()

    def _get_client(self) -> QbClient | TxClient | DelugeWebClient | None:
        """
        Return the thread-local client instance or creates a new one if it doesn't exist.

        Returns:
            The active client instance or None if connection fails.
        """
        if hasattr(self._local, "client") and self._local.client:
            return self._local.client

        logger.debug(f"Initializing new {self.client_type} client connection for thread {threading.get_ident()}...")

        safe_host = self.host or "localhost"
        safe_port = int(self.port) if self.port else 8080

        # FIX: Explicitly annotate 'client' so MyPy knows it can be ANY of the supported clients.
        # Without this, MyPy infers the type from the first assignment (e.g. QbClient) and
        # errors out when a different type (e.g. TxClient) is assigned in an elif block.
        client: QbClient | TxClient | DelugeWebClient | None = None

        try:
            if self.client_type == TorrentClientType.QBITTORRENT:
                qb = QbClient(
                    host=safe_host,
                    port=safe_port,
                    username=self.username or "",
                    password=self.password or "",
                )
                qb.auth_log_in()
                client = qb

            elif self.client_type == TorrentClientType.TRANSMISSION:
                # Validated in Config.validate to be http/https
                safe_scheme = cast(Literal["http", "https"], self.scheme)
                client = TxClient(
                    host=safe_host,
                    port=safe_port,
                    protocol=safe_scheme,
                    username=self.username,
                    password=self.password,
                    timeout=30,
                )

            elif self.client_type == TorrentClientType.DELUGE:
                dw = DelugeWebClient(url=self.dl_url or "", password=self.password or "")
                dw.login()
                client = dw

            else:
                raise ValueError(f"Unsupported download client configured: {self.client_type}")

            # Store in thread-local
            self._local.client = client

        except Exception as e:
            logger.error(f"Error initializing torrent client: {e}", exc_info=True)
            self._local.client = None

        return getattr(self._local, "client", None)

    def verify_credentials(self) -> bool:
        """
        Verify if the client can connect with the provided credentials.

        Returns:
            bool: True if connected successfully, False otherwise.
        """
        if self._get_client():
            logger.info(f"Successfully connected to {self.client_type}")
            return True

        logger.warning(f"Could not connect to {self.client_type} at startup.")
        return False

    @staticmethod
    def _format_size(size_bytes: int | float | str | None) -> str:
        """
        Format bytes into human-readable B, KB, MB, GB, TB, PB.

        Args:
            size_bytes: The size in bytes (can be int, float, or valid numeric string).

        Returns:
            str: Human readable size string (e.g. "1.50 GB") or "Unknown".
        """
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

    def add_magnet(self, magnet_link: str, save_path: str) -> None:
        """
        Add a magnet link to the configured torrent client.

        Args:
            magnet_link: The magnet URI.
            save_path: The filesystem path where data should be saved.

        Returns:
            None
        """
        try:
            self._add_magnet_logic(magnet_link, save_path)
        except Exception as e:
            logger.warning(f"Failed to add torrent ({e}). Attempting to reconnect and retry...", exc_info=True)
            self._local.client = None  # Clear bad connection
            self._add_magnet_logic(magnet_link, save_path)

    def _add_magnet_logic(self, magnet_link: str, save_path: str) -> None:
        """
        Internal logic to add magnet link.

        Args:
            magnet_link: The magnet URI.
            save_path: The filesystem path where data should be saved.
        """
        client = self._get_client()
        if not client:
            raise ConnectionError("Torrent client is not connected.")

        logger.info(f"Adding torrent to {self.client_type} at {save_path}")

        if self.client_type == TorrentClientType.QBITTORRENT:
            qb_client = cast(QbClient, client)
            result = qb_client.torrents_add(urls=magnet_link, save_path=save_path, category=self.category)
            if isinstance(result, str) and result.lower() != "ok.":
                logger.warning(f"qBittorrent add returned unexpected response: {result}")

        elif self.client_type == TorrentClientType.TRANSMISSION:
            tx_client = cast(TxClient, client)
            try:
                tx_client.add_torrent(magnet_link, download_dir=save_path, labels=[self.category])
            except Exception as e:
                logger.warning(f"Transmission label assignment failed: {e}. Retrying without labels.")
                tx_client.add_torrent(magnet_link, download_dir=save_path)

        elif self.client_type == TorrentClientType.DELUGE:
            deluge_client = cast(DelugeWebClient, client)
            try:
                deluge_client.add_torrent_magnet(magnet_link, save_directory=save_path, label=self.category)
            except Exception as e:
                error_msg = str(e).lower()
                if "label" in error_msg or "unknown parameter" in error_msg:
                    logger.warning(
                        f"Deluge Plugin Error ({e}). Adding torrent without category (Label plugin likely disabled)."
                    )
                    try:
                        deluge_client.add_torrent_magnet(magnet_link, save_directory=save_path)
                    except Exception as e2:
                        logger.error(f"Deluge fallback failed: {e2}", exc_info=True)
                        raise e2
                else:
                    raise e

    def remove_torrent(self, torrent_id: str) -> None:
        """
        Remove a torrent by ID.

        Args:
            torrent_id: The hash or ID of the torrent to remove.

        Returns:
            None
        """
        try:
            self._remove_torrent_logic(torrent_id)
        except Exception as e:
            logger.warning(f"Failed to remove torrent ({e}). Attempting to reconnect and retry...", exc_info=True)
            self._local.client = None
            self._remove_torrent_logic(torrent_id)

    def _remove_torrent_logic(self, torrent_id: str) -> None:
        """
        Internal logic to remove torrent.

        Args:
            torrent_id: The hash or ID.
        """
        client = self._get_client()
        if not client:
            raise ConnectionError("Torrent client is not connected.")

        logger.info(f"Removing torrent {torrent_id} from {self.client_type}")

        if self.client_type == TorrentClientType.QBITTORRENT:
            qb_client = cast(QbClient, client)
            qb_client.torrents_delete(torrent_hashes=torrent_id, delete_files=False)

        elif self.client_type == TorrentClientType.TRANSMISSION:
            tx_client = cast(TxClient, client)
            tid: int | str
            try:
                tid = int(torrent_id)
            except ValueError:
                tid = torrent_id
                logger.debug(f"Transmission: ID {torrent_id} is not an integer, using as string hash.")
            tx_client.remove_torrent(ids=[tid], delete_data=False)

        elif self.client_type == TorrentClientType.DELUGE:
            deluge_client = cast(DelugeWebClient, client)
            deluge_client.remove_torrent(torrent_id, remove_data=False)

    def get_status(self) -> list[TorrentStatus]:
        """
        Retrieve the status of current downloads in the configured category.

        Returns:
            list[TorrentStatus]: A list of dictionaries containing standardized torrent details.
        """
        try:
            return self._get_status_logic()
        except Exception as e:
            logger.warning(f"Failed to get status ({e}). Reconnecting...", exc_info=True)
            self._local.client = None
            return self._get_status_logic()

    def _get_status_logic(self) -> list[TorrentStatus]:
        """
        Internal logic to fetch status from the client.

        Raises:
            ConnectionError: If the client is not connected.
        """
        client = self._get_client()
        if not client:
            raise ConnectionError("Torrent client is not connected.")

        results: list[TorrentStatus] = []

        if self.client_type == TorrentClientType.TRANSMISSION:
            tx_client = cast(TxClient, client)
            # Use specific variable to avoid scope leaking and type collision
            tx_torrents = tx_client.get_torrents()
            for tx_torrent in tx_torrents:
                results.append(
                    {
                        "id": str(tx_torrent.id),
                        "name": tx_torrent.name,
                        "progress": round(tx_torrent.progress * 100, 2) if tx_torrent.progress else 0.0,
                        # SAFETY: Explicitly cast to string to avoid Enum issues with older/newer versions
                        "state": str(tx_torrent.status),
                        "size": self._format_size(tx_torrent.total_size),
                    }
                )

        elif self.client_type == TorrentClientType.QBITTORRENT:
            qb_client = cast(QbClient, client)
            qb_torrents = cast(list[QbTorrentProtocol], qb_client.torrents_info(category=self.category))
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

        elif self.client_type == TorrentClientType.DELUGE:
            deluge_client = cast(DelugeWebClient, client)
            deluge_torrents = deluge_client.get_torrents_status(
                filter_dict={"label": self.category},
                keys=["name", "state", "progress", "total_size"],
            )
            if deluge_torrents.result is not None:
                if isinstance(deluge_torrents.result, dict):
                    results_dict = deluge_torrents.result
                    for key, deluge_data in results_dict.items():
                        # Strict type check for safety
                        if not isinstance(deluge_data, dict):
                            continue

                        progress_val = deluge_data.get("progress")
                        try:
                            if progress_val is None:
                                progress = 0.0
                            else:
                                progress = round(float(progress_val), 2)
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
