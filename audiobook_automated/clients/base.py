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
    # Core Task 4: Add category field to allow validation before deletion
    category: str | None = None


class TorrentClientStrategy(ABC):
    """Abstract base class for torrent client strategies."""

    # Plugin Configuration Contracts
    # Subclasses should override this to define their default port.
    DEFAULT_PORT: ClassVar[int] = 8080

    def __init__(  # noqa: PLR0913
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        scheme: str = "http",
        timeout: int = 30,
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
        self.timeout = timeout

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

    def __del__(self) -> None:
        """Ensure resources are released when the strategy instance is garbage collected.

        This acts as a safety net for thread-local instances that might not be explicitly closed.
        """
        try:
            self.close()
        except Exception:  # noqa: S110
            # Swallow errors during GC to prevent noisy stderr output
            pass
