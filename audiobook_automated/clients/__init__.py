# audiobook_automated/clients/__init__.py
"""Torrent clients package."""

from .base import TorrentClientStrategy, TorrentStatus
from .manager import TorrentManager

__all__ = ["TorrentManager", "TorrentClientStrategy", "TorrentStatus"]
