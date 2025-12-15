# stubs/deluge_web_client/__init__.pyi
import contextlib
from typing import Any, TypedDict

# Define strict types for the options dict to prevent typo bugs
class TorrentOptions(TypedDict, total=False):
    add_paused: bool
    auto_managed: bool
    download_location: str
    seed_mode: bool
    label: str  # Added: Used in deluge.py

# Define the structure of the RPC response
class Response:
    result: Any
    error: Any
    id: int

class DelugeWebClient(contextlib.AbstractContextManager["DelugeWebClient"]):
    def __init__(self, url: str, password: str) -> None: ...

    # Connection management
    def login(self) -> Response: ...
    def disconnect(self) -> None: ...

    # Context manager support (Fixes abstract attribute errors)
    def __enter__(self) -> DelugeWebClient: ...
    def __exit__(self, *args: Any) -> None: ...

    # Methods used in deluge.py
    def get_plugins(self) -> Response: ...
    def add_torrent_magnet(self, magnet_link: str, torrent_options: TorrentOptions | None = ...) -> Any: ...
    def remove_torrent(self, torrent_id: str, remove_data: bool = ...) -> Any: ...
    def get_torrents_status(
        self, filter_dict: dict[str, Any] | None = ..., keys: list[str] | None = ...
    ) -> Response: ...

    # Kept from previous stub
    def upload_torrent(self, torrent_path: str, torrent_options: TorrentOptions | None = ...) -> Response: ...
