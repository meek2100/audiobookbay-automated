# File: audiobook_automated/clients/putio.py
"""Strategy implementation for Put.io cloud torrent client."""

import logging
import os
from typing import Any, override

import requests
from requests.sessions import Session

from audiobook_automated.utils import format_size

from .base import TorrentClientStrategy, TorrentStatus

logger = logging.getLogger(__name__)


class Strategy(TorrentClientStrategy):
    """Strategy implementation for Put.io."""

    DEFAULT_PORT = 443

    def __init__(  # noqa: PLR0913
        self,
        *args: Any,
        token: str | None = None,
        folder_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Put.io strategy.

        Args:
            *args: Standard strategy arguments (host, port, username, password, scheme, timeout).
            token: Put.io OAuth access token.
            folder_id: Optional Put.io destination folder ID (defaults to root '0').
            **kwargs: Extra arbitrary arguments.
        """
        super().__init__(*args, **kwargs)
        self.token = token or self.password or os.getenv("PUTIO_TOKEN")
        self.folder_id = folder_id or os.getenv("PUTIO_FOLDER_ID", "0")
        self.session: Session | None = None

        if self.host in ("localhost", "0.0.0.0", "127.0.0.1", ""):
            self.base_url = "https://api.put.io/v2"
        else:
            self.base_url = f"{self.scheme}://{self.host}:{self.port}/v2"

    @override
    def connect(self) -> None:
        """Establish connection session to the Put.io client.

        Raises:
            ConnectionError: If no OAuth token is provided.
        """
        if not self.token:
            raise ConnectionError("Put.io OAuth token not configured (set PUTIO_TOKEN or DL_PASSWORD).")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            }
        )

    @override
    def close(self) -> None:
        """Close the Put.io session and release socket pool."""
        if self.session:
            self.session.close()
            self.session = None

    @override
    def verify_credentials(self) -> bool:
        """Verify that the provided Put.io credentials work."""
        try:
            if not self.session:
                self.connect()

            resp = self.session.get(f"{self.base_url}/account/info", timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status") == "OK"
            return False
        except Exception:
            return False

    @override
    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        """Add a magnet link to Put.io transfers.

        Args:
            magnet_link: The full magnet URI.
            save_path: The filesystem path (unused by Put.io cloud).
            category: Category/label (unused by Put.io transfers).

        Raises:
            ConnectionError: If client is not connected.
            RuntimeError: If Put.io API returns an error.
        """
        if not self.session:
            self.connect()

        payload = {
            "url": magnet_link,
            "save_parent_id": self.folder_id,
        }
        resp = self.session.post(f"{self.base_url}/transfers/add", data=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Put.io add transfer failed: HTTP {resp.status_code} - {resp.text}")

        data = resp.json()
        if data.get("status") != "OK":
            raise RuntimeError(f"Put.io add transfer returned non-OK status: {data.get('error_message', data)}")

    @override
    def get_status(self, category: str) -> list[TorrentStatus]:
        """Retrieve status of active Put.io transfers.

        Args:
            category: Filter category (Put.io transfers are account-wide).

        Returns:
            list[TorrentStatus]: Normalized list of transfers.
        """
        if not self.session:
            self.connect()

        resp = self.session.get(f"{self.base_url}/transfers/list", timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Put.io list transfers failed: HTTP {resp.status_code} - {resp.text}")

        data = resp.json()
        transfers = data.get("transfers", [])
        results: list[TorrentStatus] = []

        for t in transfers:
            raw_progress = t.get("percent_done") or 0.0
            progress = round(float(raw_progress), 2)

            size_bytes = t.get("size") or 0
            if size_bytes == 0:
                size_str = "fetching meta.."
            else:
                size_str = format_size(size_bytes)

            state_raw = str(t.get("status", "Unknown"))
            state = state_raw.capitalize()

            results.append(
                TorrentStatus(
                    id=str(t.get("id", "")),
                    name=t.get("name") or "Unknown",
                    progress=progress,
                    state=state,
                    size=size_str,
                    category=category,
                )
            )

        return results

    @override
    def remove_torrent(self, torrent_id: str) -> None:
        """Cancel/remove a transfer from Put.io by ID.

        Args:
            torrent_id: The Put.io transfer ID.

        Raises:
            ConnectionError: If client is not connected.
            RuntimeError: If cancellation fails.
        """
        if not self.session:
            self.connect()

        payload = {"transfer_ids": str(torrent_id)}
        resp = self.session.post(f"{self.base_url}/transfers/cancel", data=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Put.io cancel transfer failed: HTTP {resp.status_code} - {resp.text}")

        data = resp.json()
        if data.get("status") != "OK":
            raise RuntimeError(f"Put.io cancel transfer returned non-OK status: {data.get('error_message', data)}")
