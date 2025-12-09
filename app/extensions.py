"""Extensions module initializing Flask extensions."""

from concurrent.futures import ThreadPoolExecutor

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

from .clients import TorrentManager
from .config import Config

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
# Uses Config directly since this is a module-level initialization.
executor = ThreadPoolExecutor(max_workers=Config.SCRAPER_THREADS)
