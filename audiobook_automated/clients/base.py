# File: audiobook_automated/clients/base.py
"""Base classes and types for torrent clients."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass
class TorrentStatus:
    """Dataclass representing a standardized torrent status object."""

    id: str | int
    name: str
    progress: float
    state: str
    size: str


class TorrentClientStrategy(ABC):
    """Abstract base class for torrent client strategies."""

    # Plugin Configuration Contracts
    # Subclasses should override this to define their default port.
    DEFAULT_PORT: ClassVar[int] = 8080

    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        scheme: str = "http",
        **kwargs: Any,
    ) -> None:
        """Initialize the client strategy configuration.

        Accepts **kwargs to allow subclasses to accept extra parameters
        without breaking the common interface.
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.scheme = scheme

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the torrent client."""
        pass  # pragma: no cover

    @abstractmethod
    def close(self) -> None:
        """Close the connection to the torrent client and release resources."""
        pass  # pragma: no cover

    @abstractmethod
    def add_magnet(self, magnet_link: str, save_path: str, category: str) -> None:
        """Add a magnet link to the client."""
        pass  # pragma: no cover

    @abstractmethod
    def remove_torrent(self, torrent_id: str) -> None:
        """Remove a torrent by ID."""
        pass  # pragma: no cover

    @abstractmethod
    def get_status(self, category: str) -> list[TorrentStatus]:
        """Retrieve status of torrents in the given category."""
        pass  # pragma: no cover
