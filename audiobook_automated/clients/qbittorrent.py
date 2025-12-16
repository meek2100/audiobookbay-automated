"""Strategy implementation for qBittorrent."""

import logging
from typing import Any, Protocol, cast

from qbittorrentapi import Client as QbClient

from .base import TorrentClientStrategy, TorrentStatus

logger = logging.getLogger(__name__)


class QbTorrentProtocol(Protocol):
    """Protocol defining the expected structure of a qBittorrent torrent object."""

    hash: str
    name: str
    state: str
    total_size: int
    progress: float


class Strategy(TorrentClientStrategy):
    """Strategy implementation for qBittorrent."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the qBittorrent strategy."""
        super().__init__(*args, **kwargs)
        self.client: QbClient | None = None

    def connect(self) -> None:
        """Connect to the qBittorrent client."""
        self.client = QbClient(
            host=self.host,
            port=self.port,
            username=self.username or "",
            password=self.password or "",
            REQUESTS_ARGS={"timeout": 30},
        )
        self.client.auth_log_in()

    def close(self) -> None:
        """Close the qBittorrent client session."""
        if self.client:
            try:
                # qBittorrentAPI doesn't strictly require logout, but it's good practice
                self.client.auth_log_out()
            except Exception as e:
                logger.debug(f"Error closing qBittorrent connection: {e}")
            self.client = None

    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        """Add a magnet link to qBittorrent."""
        if not self.client:
            raise ConnectionError("qBittorrent client not connected")

        # qBittorrent API v2.14+ returns JSON metadata, older versions return 'Ok.' or 'Fails.'
        result = self.client.torrents_add(urls=magnet_link, save_path=save_path, category=category)

        # Check for legacy string failure response
        if isinstance(result, str) and result.lower() == "fails.":
            logger.warning(f"qBittorrent returned failure response: {result}")

    def remove_torrent(self, torrent_id: str) -> None:
        """Remove a torrent from qBittorrent."""
        if not self.client:
            raise ConnectionError("qBittorrent client not connected")
        self.client.torrents_delete(torrent_hashes=torrent_id, delete_files=False)

    def get_status(self, category: str) -> list[TorrentStatus]:
        """Get torrent status from qBittorrent."""
        if not self.client:
            raise ConnectionError("qBittorrent client not connected")
        results: list[TorrentStatus] = []
        # qBittorrent supports server-side filtering by category
        qb_torrents = cast(list[QbTorrentProtocol], self.client.torrents_info(category=category))
        for qb_torrent in qb_torrents:
            results.append(
                {
                    "id": qb_torrent.hash,
                    "name": qb_torrent.name,
                    # qB API returns progress as 0.0-1.0 float, normalize to 0.0-100.0
                    "progress": round(qb_torrent.progress * 100, 2) if qb_torrent.progress else 0.0,
                    "state": qb_torrent.state,
                    "size": self._format_size(qb_torrent.total_size),
                }
            )
        return results
