# File: audiobook_automated/clients/deluge.py
"""Strategy implementation for Deluge."""

import logging
from typing import Any

from deluge_web_client import DelugeWebClient
from deluge_web_client.schema import TorrentOptions

from audiobook_automated.utils import format_size

from .base import TorrentClientStrategy, TorrentStatus

logger = logging.getLogger(__name__)


class Strategy(TorrentClientStrategy):
    """Strategy implementation for Deluge."""

    DEFAULT_PORT = 8112

    def __init__(self, dl_url: str | None = None, *args: Any, **kwargs: Any) -> None:
        """Initialize the Deluge strategy.

        Args:
            dl_url: Optional override for the Deluge URL.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self.dl_url = dl_url
        self.client: DelugeWebClient | None = None
        self.label_plugin_enabled: bool = False

    def connect(self) -> None:
        """Connect to the Deluge client."""
        # DelugeWebClient uses the full URL
        url = self.dl_url or f"{self.scheme}://{self.host}:{self.port}"
        self.client = DelugeWebClient(url=url, password=self.password or "")

        # Check login result
        response = self.client.login()
        # Explicitly check for RPC errors as the client might not raise them automatically
        if response.error:
            # Raise exception so TorrentManager knows connection failed and can retry/log
            raise ConnectionError(f"Failed to login to Deluge: {response.error}")

        # Detect Plugins (Specifically 'Label')
        try:
            plugins_resp = self.client.get_plugins()
            # Narrow the type: verify it is a list or dict before checking for membership
            if isinstance(plugins_resp.result, (list, dict)) and "Label" in plugins_resp.result:
                self.label_plugin_enabled = True
                logger.info("Deluge 'Label' plugin detected.")
            else:
                self.label_plugin_enabled = False
                logger.info("Deluge 'Label' plugin NOT detected. Categorization will be disabled.")
        except Exception as e:
            logger.warning(f"Could not verify Deluge plugins: {e}. Defaulting to no labels.")
            self.label_plugin_enabled = False

    def close(self) -> None:
        """Close the Deluge client session."""
        # DelugeWebClient doesn't hold a persistent socket, just release the object
        self.client = None

    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        """Add a magnet link to Deluge."""
        if not self.client:
            raise ConnectionError("Deluge client not connected")

        # Configure options based on plugin availability
        if self.label_plugin_enabled:
            options = TorrentOptions(download_location=save_path, label=category)
        else:
            options = TorrentOptions(download_location=save_path)

        try:
            self.client.add_torrent_magnet(magnet_link, torrent_options=options)
        except Exception as e:
            # Fallback: If we tried with a label and it failed, retry without it
            # This handles cases where detection gave a false positive or transient error
            error_msg = str(e).lower()
            if self.label_plugin_enabled and ("label" in error_msg or "unknown parameter" in error_msg):
                logger.warning(
                    f"Deluge Label error despite plugin detection ({e}). "
                    "Downgrading to label-less download for this torrent."
                )
                try:
                    fallback_options = TorrentOptions(download_location=save_path)
                    self.client.add_torrent_magnet(magnet_link, torrent_options=fallback_options)
                    return
                except Exception as e2:
                    logger.error(f"Deluge fallback failed: {e2}", exc_info=True)
                    raise e2

            raise

    def remove_torrent(self, torrent_id: str) -> None:
        """Remove a torrent from Deluge."""
        if not self.client:
            raise ConnectionError("Deluge client not connected")
        self.client.remove_torrent(torrent_id, remove_data=False)

    def get_status(self, category: str) -> list[TorrentStatus]:
        """Get torrent status from Deluge."""
        if not self.client:
            raise ConnectionError("Deluge client not connected")
        results: list[TorrentStatus] = []

        # If Label plugin is enabled, filter by our category.
        # If NOT enabled, we must fetch ALL torrents to ensure the user can see their downloads.
        # (Filtering by label is impossible without the plugin).
        filter_dict: dict[str, Any] = {}
        if self.label_plugin_enabled:
            filter_dict["label"] = category

        # This call handles raising DelugeWebClientError if auth fails (handled by execute_call)
        deluge_torrents = self.client.get_torrents_status(
            filter_dict=filter_dict,
            keys=["name", "state", "progress", "total_size"],
        )

        if deluge_torrents.result is not None:
            if isinstance(deluge_torrents.result, dict):
                results_dict = deluge_torrents.result
                for key, deluge_data in results_dict.items():
                    # Robust check for None or invalid type to please type checkers
                    if deluge_data is None or not isinstance(deluge_data, dict):
                        continue
                    progress_val = deluge_data.get("progress")
                    try:
                        # Deluge returns progress as 0-100 float
                        progress = round(float(progress_val), 2) if progress_val is not None else 0.0
                    except (ValueError, TypeError):
                        progress = 0.0

                    results.append(
                        {
                            "id": key,
                            "name": deluge_data.get("name", "Unknown"),
                            "progress": progress,
                            "state": deluge_data.get("state", "Unknown"),
                            # FIX: Use public utility format_size
                            "size": format_size(deluge_data.get("total_size")),
                        }
                    )
            else:
                logger.warning(f"Deluge returned unexpected data type: {type(deluge_torrents.result)}")
        else:
            logger.warning("Deluge returned empty or invalid result payload.")
        return results
