"""Network module handling HTTP sessions, proxies, and mirrors."""

import concurrent.futures
import json
import logging
import os
import random
import threading
from typing import cast

import requests
from cachetools import TTLCache
from flask import current_app
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util.retry import Retry

from audiobook_automated.constants import DEFAULT_MIRRORS, DEFAULT_TRACKERS, USER_AGENTS
from audiobook_automated.scraper.parser import BookDict

logger = logging.getLogger(__name__)

# --- Concurrency Control ---
# Default concurrency limit (overridden by init_semaphore via config)
DEFAULT_CONCURRENT_REQUESTS = 3
# Internal semaphore reference, initialized lazily or with default
_semaphore: threading.BoundedSemaphore = threading.BoundedSemaphore(DEFAULT_CONCURRENT_REQUESTS)
# Lock to ensure thread-safe operations on shared caches (search_cache, mirror_cache)
CACHE_LOCK = threading.Lock()

# --- Thread-Local Storage ---
# Stores objects that are not thread-safe (e.g. requests.Session) to ensure
# unique instances per thread while allowing reuse across multiple requests within that thread.
_thread_local = threading.local()

# --- Caches ---
# Explicit type parameters for TTLCache to satisfy strict MyPy
mirror_cache: TTLCache[str, str | None] = TTLCache(maxsize=1, ttl=600)
# Short-lived cache for connection failures (Negative Caching) to prevent retry storms
failure_cache: TTLCache[str, bool] = TTLCache(maxsize=1, ttl=30)

search_cache: TTLCache[str, list[BookDict]] = TTLCache(maxsize=100, ttl=300)
details_cache: TTLCache[str, BookDict] = TTLCache(maxsize=100, ttl=300)
tracker_cache: TTLCache[str, list[str]] = TTLCache(maxsize=1, ttl=300)


def init_semaphore(max_requests: int) -> None:
    """Initialize the global request semaphore with a specific limit.

    Args:
        max_requests: The maximum number of concurrent external requests allowed.
    """
    global _semaphore
    logger.info(f"Initializing Global Request Semaphore with limit: {max_requests}")
    _semaphore = threading.BoundedSemaphore(max_requests)


def get_semaphore() -> threading.BoundedSemaphore:
    """Retrieve the global request semaphore.

    Returns:
        threading.BoundedSemaphore: The active semaphore.
    """
    return _semaphore


def get_random_user_agent() -> str:
    """Return a random User-Agent string from the constants list."""
    return random.choice(USER_AGENTS)  # nosec B311


def get_trackers() -> list[str]:
    """Load trackers from configuration and optional local JSON file.

    Uses TTLCache to avoid repeated I/O while allowing config updates to propagate.
    Prioritizes:
    1. Environment Variable (via Config)
    2. trackers.json (Volume Mount)
    3. Internal Defaults

    Returns:
        list[str]: A list of tracker URLs.
    """
    # Check Cache
    with CACHE_LOCK:
        if "default" in tracker_cache:
            return tracker_cache["default"]

    # 1. Configured via Env/Config
    # We must access current_app inside the function (request time), not at module level
    env_trackers = current_app.config.get("MAGNET_TRACKERS", [])
    if env_trackers:
        result = cast(list[str], env_trackers)
        with CACHE_LOCK:
            tracker_cache["default"] = result
        return result

    # 2. Volume Mount Override
    json_path = os.path.join(os.getcwd(), "trackers.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    logger.info("Loaded custom trackers from trackers.json")
                    with CACHE_LOCK:
                        tracker_cache["default"] = cast(list[str], data)
                    return cast(list[str], data)
                else:
                    logger.warning("trackers.json contains invalid data (expected a list). Using defaults.")
        except Exception as e:
            logger.warning(f"Failed to load trackers.json: {e}", exc_info=True)

    # 3. Defaults
    with CACHE_LOCK:
        tracker_cache["default"] = DEFAULT_TRACKERS
    return DEFAULT_TRACKERS


def get_mirrors() -> list[str]:
    """Retrieve the list of mirrors to attempt, in priority order.

    Combines the primary hostname, user-defined mirrors, and default mirrors.
    """
    primary = current_app.config.get("ABB_HOSTNAME", "audiobookbay.lu")
    extra = current_app.config.get("ABB_MIRRORS", [])

    # Start with user preference
    candidates = [primary] + extra + DEFAULT_MIRRORS

    # Deduplicate while preserving order
    return list(dict.fromkeys(candidates))


def get_session() -> Session:
    """Configure and return a requests Session with retry logic.

    Returns:
        Session: A configured requests Session object.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_ping_session() -> Session:
    """Configure and return a requests Session with ZERO retries for availability checks.

    This prevents 'retry storms' where a dead mirror holds up a thread for 25+ seconds.
    We want the check to fail fast (5s timeout, 0 retries).

    Returns:
        Session: A configured requests Session object with 0 retries.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=0,
        backoff_factor=0,
        status_forcelist=[],
        allowed_methods=["HEAD", "GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_thread_session() -> Session:
    """Retrieve or create a thread-local Session.

    This optimizes performance by reusing the TCP/TLS connection for multiple
    requests made by the same thread (e.g. during pagination or search),
    while ensuring thread safety.

    Returns:
        Session: The active thread-local session.
    """
    if not hasattr(_thread_local, "session"):
        _thread_local.session = get_session()
    return cast(Session, _thread_local.session)


def get_headers(user_agent: str | None = None, referer: str | None = None) -> dict[str, str]:
    """Generate standard HTTP headers for scraping requests.

    Args:
        user_agent: Optional custom User-Agent string.
        referer: Optional Referer header string.

    Returns:
        dict[str, str]: A dictionary of HTTP headers.
    """
    if not user_agent:
        user_agent = get_random_user_agent()
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def check_mirror(hostname: str) -> str | None:
    """Check if a mirror is reachable via HEAD or GET request.

    Uses a zero-retry session to fail fast.

    Args:
        hostname: The domain name to check (e.g., "audiobookbay.lu").

    Returns:
        str | None: The hostname if reachable, otherwise None.
    """
    url = f"https://{hostname}/"
    headers = get_headers()
    session = get_ping_session()

    try:
        response = session.head(url, headers=headers, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return hostname
    except (requests.Timeout, requests.RequestException):
        pass

    try:
        response = session.get(url, headers=headers, timeout=5, stream=True)
        response.close()
        if response.status_code == 200:
            return hostname
    except (requests.Timeout, requests.RequestException):
        pass

    return None


def find_best_mirror() -> str | None:
    """Find the first reachable AudiobookBay mirror from the configured list.

    Uses threaded checks for speed.
    Implements Negative Caching: If no mirrors work, backs off for 30s.

    Returns:
        str | None: The hostname of the active mirror, or None if all fail.
    """
    # 1. Check Negative Cache (Backoff)
    with CACHE_LOCK:
        if "failure" in failure_cache:
            logger.debug("Skipping mirror check due to recent failure (Negative Cache hit).")
            return None

    # 2. Check Positive Cache
    cache_key = "active_mirror"
    with CACHE_LOCK:
        if cache_key in mirror_cache:
            return mirror_cache[cache_key]

    # Dynamic retrieval of mirrors list
    mirrors = get_mirrors()

    logger.debug(f"Checking connectivity for {len(mirrors)} mirrors...")
    safe_mirror_workers = 5

    # PERFORMANCE: Use raw Executor to prevent implicit waiting on slow mirrors
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=safe_mirror_workers)
    futures = [executor.submit(check_mirror, host) for host in mirrors]

    try:
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                logger.info(f"Found active mirror: {result}")
                # Optimization: Cancel other pending futures since we found a winner
                # (Best effort, running threads won't stop but pending ones will be cancelled)
                for f in futures:
                    f.cancel()

                # CACHE UPDATE: Cache successful result
                with CACHE_LOCK:
                    mirror_cache[cache_key] = result
                return result
    finally:
        # CLEANUP: Shutdown executor without waiting for straggler threads.
        # This prevents the function from blocking for the full timeout of a dead mirror.
        executor.shutdown(wait=False)

    logger.error("No working AudiobookBay mirrors found! Caching failure for 30s.")
    # CACHE UPDATE: Cache failure (Negative Caching)
    with CACHE_LOCK:
        failure_cache["failure"] = True
    return None
