# File: audiobook_automated/extensions.py
"""Extensions module initializing Flask extensions."""

import logging
import signal
import sys
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from types import FrameType

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
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

# Initialize Security Headers (Talisman)
# Note: Configuration happens in __init__.py/create_app
talisman = Talisman()

# Initialize Torrent Manager
torrent_manager = TorrentManager()


class ScraperExecutor:
    """Wrapper for ThreadPoolExecutor to allow lazy initialization with Flask config.

    This ensures that the executor respects the 'SCRAPER_THREADS' config value
    at the time the application starts (create_app), rather than locking in
    an environment variable at import time.
    """

    def __init__(self) -> None:
        """Initialize the ScraperExecutor."""
        self._executor: ThreadPoolExecutor | None = None

    def init_app(self, app: Flask) -> None:
        """Initialize the executor with the configured thread count.

        Args:
            app: The Flask application instance.
        """
        # Defaults to 3 if not set (matching previous Config default)
        max_workers = app.config.get("SCRAPER_THREADS", 3)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

        # NOTE: Semaphore initialization has been moved to app/__init__.py
        # to prevent circular imports between extensions.py and scraper/network.py

    def submit[T, **P](self, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> Future[T]:
        """Submit a callable to be executed with the given arguments.

        Proxies the call to the underlying ThreadPoolExecutor.

        Raises:
            RuntimeError: If init_app() has not been called yet.
        """
        if not self._executor:
            raise RuntimeError("Executor not initialized. Call init_app() first.")
        return self._executor.submit(fn, *args, **kwargs)

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor."""
        if self._executor:
            self._executor.shutdown(wait=wait)


# GLOBAL EXECUTOR: Shared thread pool for concurrent scraping.
# Initialized in create_app via init_app().
executor = ScraperExecutor()


def register_shutdown_handlers(app: Flask) -> None:  # noqa: ARG001
    """Register signal handlers for graceful shutdown."""
    from audiobook_automated.scraper.network import shutdown_network  # noqa: PLC0415

    def shutdown_handler(signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signals."""
        logging.info(f"Received signal {signum}. Shutting down...")
        executor.shutdown(wait=False)
        shutdown_network()
        sys.exit(0)

    # Register handlers for SIGTERM and SIGINT
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
