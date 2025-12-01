import logging
import os

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

    def __init__(self):
        self.client_type = os.getenv("DOWNLOAD_CLIENT")
        self.host = os.getenv("DL_HOST")
        self.port = os.getenv("DL_PORT")
        self.username = os.getenv("DL_USERNAME")
        self.password = os.getenv("DL_PASSWORD")
        self.category = os.getenv("DL_CATEGORY", "abb-downloader")
        self.scheme = os.getenv("DL_SCHEME", "http")

        # Normalize connection URL for Deluge
        self.dl_url = os.getenv("DL_URL")
        if not self.dl_url and self.host and self.port:
            self.dl_url = f"{self.scheme}://{self.host}:{self.port}"

        self._client = None

    def _get_client(self):
        """
        Returns the existing client instance or creates a new one if it doesn't exist.
        """
        if self._client:
            return self._client

        logger.debug(f"Initializing new {self.client_type} client connection...")

        try:
            if self.client_type == "qbittorrent":
                try:
                    qb = QbClient(host=self.host, port=self.port, username=self.username, password=self.password)
                    qb.auth_log_in()
                    self._client = qb
                except LoginFailed as e:
                    logger.error("qBittorrent login failed.")
                    raise e

            elif self.client_type == "transmission":
                try:
                    self._client = TxClient(
                        host=self.host,
                        port=self.port,
                        protocol=self.scheme,
                        username=self.username,
                        password=self.password,
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

    def verify_credentials(self):
        client = self._get_client()
        if client:
            logger.info(f"Successfully connected to {self.client_type}")
            return True
        else:
            logger.warning(f"Could not connect to {self.client_type} at startup.")
            return False

    @staticmethod
    def _format_size(size_bytes):
        """
        Formats bytes into human-readable B, KB, MB, GB, TB.
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

    def add_magnet(self, magnet_link, save_path):
        try:
            self._add_magnet_logic(magnet_link, save_path)
        except Exception as e:
            logger.warning(f"Failed to add torrent ({e}). Attempting to reconnect and retry...")
            self._client = None
            self._add_magnet_logic(magnet_link, save_path)

    def _add_magnet_logic(self, magnet_link, save_path):
        client = self._get_client()
        if not client:
            raise ConnectionError("Torrent client is not connected.")

        logger.info(f"Adding torrent to {self.client_type} at {save_path}")

        if self.client_type == "qbittorrent":
            client.torrents_add(urls=magnet_link, save_path=save_path, category=self.category)

        elif self.client_type == "transmission":
            client.add_torrent(magnet_link, download_dir=save_path, labels=[self.category])

        elif self.client_type == "delugeweb":
            try:
                client.add_torrent_magnet(magnet_link, save_directory=save_path, label=self.category)
            except Exception as e:
                if "label" in str(e).lower():
                    logger.warning("Deluge Label plugin likely missing. Adding torrent without category.")
                    client.add_torrent_magnet(magnet_link, save_directory=save_path)
                else:
                    raise e

    def remove_torrent(self, torrent_id):
        """
        Removes a torrent by ID.
        Note: Configured to keep data files (soft delete) to avoid accidental data loss.
        """
        client = self._get_client()
        if not client:
            raise ConnectionError("Torrent client is not connected.")

        logger.info(f"Removing torrent {torrent_id} from {self.client_type}")

        if self.client_type == "qbittorrent":
            client.torrents_delete(torrent_hashes=torrent_id, delete_files=False)

        elif self.client_type == "transmission":
            # Transmission expects IDs as integers usually, but hashes work in some versions.
            # safe conversion if it's digit, else pass as string (hash)
            try:
                tid = int(torrent_id)
            except ValueError:
                tid = torrent_id
            client.remove_torrent(ids=[tid], delete_data=False)

        elif self.client_type == "delugeweb":
            client.remove_torrent(torrent_id, remove_data=False)

    def get_status(self):
        try:
            return self._get_status_logic()
        except Exception as e:
            logger.warning(f"Failed to get status ({e}). Reconnecting...")
            self._client = None
            return self._get_status_logic()

    def _get_status_logic(self):
        client = self._get_client()
        if not client:
            raise ConnectionError("Torrent client is not connected.")

        results = []

        if self.client_type == "transmission":
            torrents = client.get_torrents()
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
            torrents = client.torrents_info(category=self.category)
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
            torrents = client.get_torrents_status(
                filter_dict={"label": self.category},
                keys=["name", "state", "progress", "total_size"],
            )
            if torrents.result:
                for key, torrent in torrents.result.items():
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
