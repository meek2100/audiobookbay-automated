"""Extensions module initializing Flask extensions."""

import os
from concurrent.futures import ThreadPoolExecutor

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

from .clients import TorrentManager

# Initialize CSRF Protection
csrf = CSRFProtect()

# Initialize Rate Limiter with memory storage (Appliance Philosophy)
# Defaults are strictly opt-in via decorators.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
)

# Initialize Torrent Manager
torrent_manager = TorrentManager()

# GLOBAL EXECUTOR: Shared thread pool for concurrent scraping.
# Matches the PAGE_LIMIT (default 3) but allows scaling via SCRAPER_THREADS.
# Prevents overhead of spawning new threads per request.
# Defaults to 3 to match the global request semaphore.
_workers = int(os.getenv("SCRAPER_THREADS", "3"))
executor = ThreadPoolExecutor(max_workers=_workers)
