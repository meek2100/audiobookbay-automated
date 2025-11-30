import os
import logging
from qbittorrentapi import Client as QbClient
from transmission_rpc import Client as TxClient
from deluge_web_client import DelugeWebClient
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class TorrentManager:
    def __init__(self):
        self.client_type = os.getenv("DOWNLOAD_CLIENT")
        self.host = os.getenv("DL_HOST")
        self.port = os.getenv("DL_PORT")
        self.username = os.getenv("DL_USERNAME")
        self.password = os.getenv("DL_PASSWORD")
        self.category = os.getenv("DL_CATEGORY", "Audiobookbay-Audiobooks")

        # DL_URL logic for Deluge or generic use
        self.dl_url = os.getenv("DL_URL")
        if not self.dl_url and self.host and self.port:
            scheme = os.getenv("DL_SCHEME", "http")
            self.dl_url = f"{scheme}://{self.host}:{self.port}"

    def add_magnet(self, magnet_link, save_path):
        """
        Adds a magnet link to the configured torrent client.
        """
        logger.info(f"Adding torrent to {self.client_type} at {save_path}")

        if self.client_type == "qbittorrent":
            qb = QbClient(host=self.host, port=self.port, username=self.username, password=self.password)
            qb.auth_log_in()
            qb.torrents_add(urls=magnet_link, save_path=save_path, category=self.category)

        elif self.client_type == "transmission":
            # transmission-rpc expects protocol/host/port separated or a URL
            # We construct parameters based on the lib's expectations
            protocol = os.getenv("DL_SCHEME", "http")
            tx = TxClient(
                host=self.host,
                port=self.port,
                protocol=protocol,
                username=self.username,
                password=self.password
            )
            tx.add_torrent(magnet_link, download_dir=save_path)

        elif self.client_type == "delugeweb":
            dw = DelugeWebClient(url=self.dl_url, password=self.password)
            dw.login()
            dw.add_torrent_magnet(magnet_link, save_directory=save_path, label=self.category)

        else:
            raise ValueError(f"Unsupported download client configured: {self.client_type}")

    def get_status(self):
        """
        Retrieves the status of torrents in the configured category.
        Returns a list of dicts: {name, progress, state, size}
        """
        results = []

        if self.client_type == "transmission":
            protocol = os.getenv("DL_SCHEME", "http")
            tx = TxClient(
                host=self.host,
                port=self.port,
                protocol=protocol,
                username=self.username,
                password=self.password
            )
            torrents = tx.get_torrents()
            # Filter logic isn't native to all transmission RPC calls easily,
            # so we fetch all and might filter UI side or accept all.
            # The original code fetched all. We'll stick to that but handle safe parsing.
            for torrent in torrents:
                results.append({
                    "name": torrent.name,
                    "progress": round(torrent.progress, 2),
                    "state": torrent.status,
                    "size": f"{torrent.total_size / (1024 * 1024):.2f} MB",
                })

        elif self.client_type == "qbittorrent":
            qb = QbClient(host=self.host, port=self.port, username=self.username, password=self.password)
            qb.auth_log_in()
            # qBittorrent supports category filtering natively
            torrents = qb.torrents_info(category=self.category)
            for torrent in torrents:
                results.append({
                    "name": torrent.name,
                    "progress": round(torrent.progress * 100, 2),
                    "state": torrent.state,
                    "size": f"{torrent.total_size / (1024 * 1024):.2f} MB",
                })

        elif self.client_type == "delugeweb":
            dw = DelugeWebClient(url=self.dl_url, password=self.password)
            dw.login()
            torrents = dw.get_torrents_status(
                filter_dict={"label": self.category},
                keys=["name", "state", "progress", "total_size"],
            )
            if torrents.result:
                for k, torrent in torrents.result.items():
                    results.append({
                        "name": torrent["name"],
                        "progress": round(torrent["progress"], 2),
                        "state": torrent["state"],
                        "size": f"{torrent['total_size'] / (1024 * 1024):.2f} MB",
                    })

        else:
            raise ValueError(f"Unsupported download client configured: {self.client_type}")

        return results