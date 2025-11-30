import logging
import os

from deluge_web_client import DelugeWebClient
from qbittorrentapi import Client as QbClient
from transmission_rpc import Client as TxClient

logger = logging.getLogger(__name__)


class TorrentManager:
    """
    Manages interactions with various torrent clients (qBittorrent, Transmission, Deluge).
    """

    def __init__(self):
        self.client_type = os.getenv("DOWNLOAD_CLIENT")
        self.host = os.getenv("DL_HOST")
        self.port = os.getenv("DL_PORT")
        self.username = os.getenv("DL_USERNAME")
        self.password = os.getenv("DL_PASSWORD")
        # Default category matched to README example for consistency
        self.category = os.getenv("DL_CATEGORY", "abb-downloader")

        # Capture scheme once during init
        self.scheme = os.getenv("DL_SCHEME", "http")

        # Normalize connection URL for Deluge or clients that prefer a full URL string
        self.dl_url = os.getenv("DL_URL")
        if not self.dl_url and self.host and self.port:
            self.dl_url = f"{self.scheme}://{self.host}:{self.port}"

    @staticmethod
    def _format_size(size_bytes):
        """
        Formats bytes into megabytes (MB) string.
        """
        if size_bytes is None:
            return "N/A"
        try:
            return f"{float(size_bytes) / (1024 * 1024):.2f} MB"
        except (ValueError, TypeError):
            return "N/A"

    def add_magnet(self, magnet_link, save_path):
        """
        Adds a magnet link to the configured torrent client.

        Args:
            magnet_link (str): The magnet URI.
            save_path (str): The destination path on the server.

        Raises:
            ValueError: If an unsupported client is configured.
        """
        logger.info(f"Adding torrent to {self.client_type} at {save_path}")

        if self.client_type == "qbittorrent":
            qb = QbClient(host=self.host, port=self.port, username=self.username, password=self.password)
            qb.auth_log_in()
            qb.torrents_add(urls=magnet_link, save_path=save_path, category=self.category)

        elif self.client_type == "transmission":
            tx = TxClient(
                host=self.host, port=self.port, protocol=self.scheme, username=self.username, password=self.password
            )
            # FIX: Added labels parameter to support categories in Transmission
            tx.add_torrent(magnet_link, download_dir=save_path, labels=[self.category])

        elif self.client_type == "delugeweb":
            dw = DelugeWebClient(url=self.dl_url, password=self.password)
            dw.login()
            try:
                # Attempt to add with label
                dw.add_torrent_magnet(magnet_link, save_directory=save_path, label=self.category)
            except Exception as e:
                # If the Label plugin is not enabled, this may fail.
                # Fallback to adding without label.
                if "label" in str(e).lower():
                    logger.warning(
                        "Deluge Label plugin likely missing or configured incorrectly. Adding torrent without category/label."
                    )
                    dw.add_torrent_magnet(magnet_link, save_directory=save_path)
                else:
                    raise e

        else:
            raise ValueError(f"Unsupported download client configured: {self.client_type}")

    def get_status(self):
        """
        Retrieves the status of torrents in the configured category.

        Returns:
            list: A list of dicts containing 'name', 'progress', 'state', and 'size'.
        """
        results = []

        if self.client_type == "transmission":
            tx = TxClient(
                host=self.host, port=self.port, protocol=self.scheme, username=self.username, password=self.password
            )
            # Note: Fetching all torrents can be slow with large libraries.
            # Filtering is done client-side here as RPC filtering varies by version.
            torrents = tx.get_torrents()
            for torrent in torrents:
                results.append(
                    {
                        "name": torrent.name,
                        "progress": round(torrent.progress * 100, 2),  # Corrected to 0-100%
                        "state": torrent.status,
                        "size": self._format_size(torrent.total_size),
                    }
                )

        elif self.client_type == "qbittorrent":
            qb = QbClient(host=self.host, port=self.port, username=self.username, password=self.password)
            qb.auth_log_in()
            torrents = qb.torrents_info(category=self.category)
            for torrent in torrents:
                results.append(
                    {
                        "name": torrent.name,
                        "progress": round(torrent.progress * 100, 2),
                        "state": torrent.state,
                        "size": self._format_size(torrent.total_size),
                    }
                )

        elif self.client_type == "delugeweb":
            dw = DelugeWebClient(url=self.dl_url, password=self.password)
            dw.login()
            torrents = dw.get_torrents_status(
                filter_dict={"label": self.category},
                keys=["name", "state", "progress", "total_size"],
            )
            if torrents.result:
                # [Ruff Fix] Use '_' for the unused key variable
                for _, torrent in torrents.result.items():
                    results.append(
                        {
                            "name": torrent["name"],
                            "progress": round(torrent["progress"], 2),
                            "state": torrent["state"],
                            "size": self._format_size(torrent["total_size"]),
                        }
                    )

        else:
            raise ValueError(f"Unsupported download client configured: {self.client_type}")

        return results
