import logging
import os
from typing import Any

from deluge_web_client import DelugeWebClient
from qbittorrentapi import Client as QbClient
from qbittorrentapi import LoginFailed
from transmission_rpc import Client as TxClient

logger = logging.getLogger(__name__)


class TorrentManager:
    """
    Manages interactions with various torrent clients (qBittorrent, Transmission, Deluge).
    Maintains a persistent client session for efficiency.
    """

    def __init__(self) -> None:
        """
        Initializes the TorrentManager by loading configuration from environment variables.
        """
        self.client_type: str | None = os.getenv("DOWNLOAD_CLIENT")
        self.host: str | None = os.getenv("DL_HOST")
        self.port: str | None = os.getenv("DL_PORT")
        self.username: str | None = os.getenv("DL_USERNAME")
        self.password: str | None = os.getenv("DL_PASSWORD")
        self.category: str = os.getenv("DL_CATEGORY", "abb-downloader")
        self.scheme: str = os.getenv("DL_SCHEME", "http")

        # Normalize connection URL for Deluge
        self.dl_url: str | None = os.getenv("DL_URL")
        if not self.dl_url and self.host and self.port:
            self.dl_url = f"{self.scheme}://{self.host}:{self.port}"

        self._client: QbClient | TxClient | DelugeWebClient | None = None

    def _get_client(self) -> QbClient | TxClient | DelugeWebClient | None:
        """
        Returns the existing client instance or creates a new one if it doesn't exist.

        Returns:
            The active client instance or None if connection fails.
        """
        if self._client:
            return self._client

        logger.debug(f"Initializing new {self.client_type} client connection...")

        try:
            if self.client_type == "qbittorrent":
                try:
                    # OPTIMIZATION: Added timeout to prevent hanging on unresponsive clients
                    qb = QbClient(
                        host=self.host,
                        port=self.port,
                        username=self.username,
                        password=self.password,
                        requests_args={"timeout": 30},
                    )
                    qb.auth_log_in()
                    self._client = qb
                except LoginFailed as e:
                    logger.error("qBittorrent login failed.")
                    raise e

            elif self.client_type == "transmission":
                try:
                    # OPTIMIZATION: Added timeout to prevent hanging
                    self._client = TxClient(
                        host=self.host,
                        port=self.port,
                        protocol=self.scheme,
                        username=self.username,
                        password=self.password,
                        timeout=30,
                    )
                except Exception as e:
                    logger.error(f"Failed to connect to Transmission: {e}")
                    # Allow app to start even if client is down; commands will fail later.
                    return None

            elif self.client_type == "delugeweb":
                try:
                    dw = DelugeWebClient(url=self.dl_url, password=self.password)
                    dw.login()
                    self._client = dw
                except Exception as e:
                    logger.error(f"Failed to connect to Deluge: {e}")
                    # Allow app to start even if client is down; commands will fail later.
                    return None

            else:
                raise ValueError(f"Unsupported download client configured: {self.client_type}")

        except Exception as e:
            logger.error(f"Error initializing torrent client: {e}")
            self._client = None

        return self._client

    def verify_credentials(self) -> bool:
        """
        Verifies if the client can connect with the provided credentials.

        Returns:
            bool: True if connected successfully, False otherwise.
        """
        client = self._get_client()
        if client:
            logger.info(f"Successfully connected to {self.client_type}")
            return True
        else:
            logger.warning(f"Could not connect to {self.client_type} at startup.")
            return False

    @staticmethod
    def _format_size(size_bytes: int | float | str | None) -> str:
        """
        Formats bytes into human-readable B, KB, MB, GB, TB.

        Args:
            size_bytes: The size in bytes.

        Returns:
            str: Human readable size string (e.g. "1.50 GB") or "N/A".
        """
        if size_bytes is None:
            return "N/A"
        try:
            size = float(size_bytes)
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if size < 1024.0:
                    return f"{size:.2f} {unit}"
                size /= 1024.0
            return f"{size:.2f} PB"
        except (ValueError, TypeError):
            return "N/A"

    def add_magnet(self, magnet_link: str, save_path: str) -> None:
        """
        Adds a magnet link to the configured torrent client.

        Args:
            magnet_link: The magnet URI.
            save_path: The filesystem path where data should be saved.
        """
        try:
            self._add_magnet_logic(magnet_link, save_path)
        except Exception as e:
            logger.warning(f"Failed to add torrent ({e}). Attempting to reconnect and retry...")
            self._client = None
            self._add_magnet_logic(magnet_link, save_path)

    def _add_magnet_logic(self, magnet_link: str, save_path: str) -> None:
        """Internal logic to add magnet link."""
        client = self._get_client()
        if not client:
            raise ConnectionError("Torrent client is not connected.")

        logger.info(f"Adding torrent to {self.client_type} at {save_path}")

        if self.client_type == "qbittorrent":
            # Type ignore because qBittorrent client types are dynamic
            client.torrents_add(urls=magnet_link, save_path=save_path, category=self.category)  # type: ignore

        elif self.client_type == "transmission":
            client.add_torrent(magnet_link, download_dir=save_path, labels=[self.category])  # type: ignore

        elif self.client_type == "delugeweb":
            try:
                client.add_torrent_magnet(magnet_link, save_directory=save_path, label=self.category)  # type: ignore
            except Exception as e:
                if "label" in str(e).lower():
                    logger.warning("Deluge Label plugin likely missing. Adding torrent without category.")
                    client.add_torrent_magnet(magnet_link, save_directory=save_path)  # type: ignore
                else:
                    raise e

    def remove_torrent(self, torrent_id: str) -> None:
        """
        Removes a torrent by ID.
        Note: Configured to keep data files (soft delete) to avoid accidental data loss.

        Args:
            torrent_id: The hash or ID of the torrent to remove.
        """
        client = self._get_client()
        if not client:
            raise ConnectionError("Torrent client is not connected.")

        logger.info(f"Removing torrent {torrent_id} from {self.client_type}")

        if self.client_type == "qbittorrent":
            client.torrents_delete(torrent_hashes=torrent_id, delete_files=False)  # type: ignore

        elif self.client_type == "transmission":
            # Transmission expects IDs as integers usually, but hashes work in some versions.
            # safe conversion if it's digit, else pass as string (hash)
            tid: int | str
            try:
                tid = int(torrent_id)
            except ValueError:
                tid = torrent_id
            client.remove_torrent(ids=[tid], delete_data=False)  # type: ignore

        elif self.client_type == "delugeweb":
            client.remove_torrent(torrent_id, remove_data=False)  # type: ignore

    def get_status(self) -> list[dict[str, Any]]:
        """
        Retrieves the status of current downloads in the configured category.

        Returns:
            list[dict[str, Any]]: A list of dictionaries containing torrent details.
        """
        try:
            return self._get_status_logic()
        except Exception as e:
            logger.warning(f"Failed to get status ({e}). Reconnecting...")
            self._client = None
            return self._get_status_logic()

    def _get_status_logic(self) -> list[dict[str, Any]]:
        """Internal logic to fetch status."""
        client = self._get_client()
        if not client:
            raise ConnectionError("Torrent client is not connected.")

        results: list[dict[str, Any]] = []

        if self.client_type == "transmission":
            torrents = client.get_torrents()  # type: ignore
            for torrent in torrents:
                results.append(
                    {
                        "id": torrent.id,
                        "name": torrent.name,
                        "progress": round(torrent.progress * 100, 2),
                        "state": torrent.status,
                        "size": self._format_size(torrent.total_size),
                    }
                )

        elif self.client_type == "qbittorrent":
            torrents = client.torrents_info(category=self.category)  # type: ignore
            for torrent in torrents:
                results.append(
                    {
                        "id": torrent.hash,
                        "name": torrent.name,
                        "progress": round(torrent.progress * 100, 2),
                        "state": torrent.state,
                        "size": self._format_size(torrent.total_size),
                    }
                )

        elif self.client_type == "delugeweb":
            torrents = client.get_torrents_status(  # type: ignore
                filter_dict={"label": self.category},
                keys=["name", "state", "progress", "total_size"],
            )
            if torrents.result:  # type: ignore
                for key, torrent in torrents.result.items():  # type: ignore
                    results.append(
                        {
                            "id": key,
                            "name": torrent["name"],
                            "progress": round(torrent["progress"], 2),
                            "state": torrent["state"],
                            "size": self._format_size(torrent["total_size"]),
                        }
                    )

        return results
