"""Extensions module.

Initializes Flask extensions and singleton objects here to avoid circular imports.

Note:
    Flask-Limiter uses `storage_uri="memory://"` to enforce the architecture
    constraint of a single-user, self-contained appliance. This avoids the need
    for external dependencies like Redis, which would overcomplicate the deployment
    model defined in AGENTS.md.
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
