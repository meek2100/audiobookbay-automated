# File: audiobook_automated/clients/transmission.py
"""Strategy implementation for Transmission."""

import logging
from typing import Any, Literal, cast

from transmission_rpc import Client as TxClient

from .base import TorrentClientStrategy, TorrentStatus

logger = logging.getLogger(__name__)


class Strategy(TorrentClientStrategy):
    """Strategy implementation for Transmission."""

    DEFAULT_PORT = 9091

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the Transmission strategy."""
        super().__init__(*args, **kwargs)
        self.client: TxClient | None = None

    def connect(self) -> None:
        """Connect to the Transmission client."""
        # transmission-rpc expects 'http' or 'https' specifically
        safe_scheme = cast(Literal["http", "https"], self.scheme)
        self.client = TxClient(
            host=self.host,
            port=self.port,
            protocol=safe_scheme,
            username=self.username,
            password=self.password,
            timeout=30,
        )

    def close(self) -> None:
        """Close the Transmission client session."""
        # transmission-rpc Client manages its own session, but doesn't expose a clear close.
        # Dropping the reference is sufficient.
        self.client = None

    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        """Add a magnet link to Transmission."""
        if not self.client:
            raise ConnectionError("Transmission client not connected")
        try:
            # Transmission uses 'labels' (plural list)
            self.client.add_torrent(magnet_link, download_dir=save_path, labels=[category])
        except Exception as e:
            # Fallback for older Transmission versions (< RPC 15) that don't support labels
            logger.warning(f"Transmission label assignment failed (server may be old): {e}. Retrying without labels.")
            self.client.add_torrent(magnet_link, download_dir=save_path)

    def remove_torrent(self, torrent_id: str) -> None:
        """Remove a torrent from Transmission."""
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
        """Get torrent status from Transmission."""
        if not self.client:
            raise ConnectionError("Transmission client not connected")
        results: list[TorrentStatus] = []

        # Transmission RPC does not support server-side filtering by label in get_torrents.
        # We must fetch all and filter client-side.
        tx_torrents = self.client.get_torrents()

        for tx_torrent in tx_torrents:
            # Safely get labels, ensuring it's a list
            labels = getattr(tx_torrent, "labels", []) or []

            if category in labels:
                # transmission-rpc 'progress' property returns percentage (0.0-100.0)
                # NOT 0.0-1.0 like qBittorrent.
                raw_progress = tx_torrent.progress
                progress = raw_progress if raw_progress is not None else 0.0

                results.append(
                    {
                        "id": str(tx_torrent.id),
                        "name": tx_torrent.name,
                        "progress": progress,
                        "state": tx_torrent.status.name,
                        "size": self._format_size(tx_torrent.total_size),
                    }
                )
        return results
