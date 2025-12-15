# stubs/deluge_web_client/__init__.pyi
from typing import Any, ContextManager, TypedDict

# Define strict types for the options dict to prevent typo bugs
class TorrentOptions(TypedDict, total=False):
    add_paused: bool
    auto_managed: bool
    download_location: str
    seed_mode: bool

# Define the structure of the RPC response
class Response:
    result: str | bool | None
    error: dict[str, Any] | None
    id: int

class DelugeWebClient(ContextManager["DelugeWebClient"]):
    def __init__(self, url: str, password: str) -> None: ...
    def login(self) -> None: ...
    def disconnect(self) -> None: ...

    # Explicitly define the dynamic method as a static one in the stub
    def upload_torrent(self, torrent_path: str, torrent_options: TorrentOptions | None = ...) -> Response: ...
    def get_torrents_status(
        self, filter_dict: dict[str, Any] | None = ..., keys: list[str] | None = ...
    ) -> dict[str, Any]: ...
