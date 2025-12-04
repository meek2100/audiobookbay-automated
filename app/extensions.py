"""
Extensions module.
Initializes Flask extensions and singleton objects here to avoid circular imports.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

from .clients import TorrentManager

# Initialize Rate Limiter
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    headers_enabled=True,
    strategy="fixed-window",
)

# Initialize CSRF Protection
csrf = CSRFProtect()

# Initialize Torrent Manager (Singleton)
torrent_manager = TorrentManager()
