"""Network module handling HTTP sessions, proxies, and mirrors."""

import concurrent.futures
import json
import logging
import random
import threading
from pathlib import Path
from typing import cast

import requests
from cachetools import TTLCache
from flask import current_app
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util.retry import Retry

from audiobook_automated.constants import DEFAULT_MIRRORS, DEFAULT_TRACKERS, USER_AGENTS
from audiobook_automated.scraper.parser import BookDetails, BookSummary

logger = logging.getLogger(__name__)

# --- Concurrency Control ---
DEFAULT_CONCURRENT_REQUESTS = 3
_semaphore: threading.BoundedSemaphore = threading.BoundedSemaphore(DEFAULT_CONCURRENT_REQUESTS)
CACHE_LOCK = threading.Lock()

# --- Thread-Local Storage ---
_thread_local = threading.local()

# --- Persistent Session Storage ---
# Cached session for low-overhead ping/availability checks
_ping_session: Session | None = None
_ping_session_lock = threading.Lock()

# --- Caches ---
mirror_cache: TTLCache[str, str | None] = TTLCache(maxsize=1, ttl=600)
failure_cache: TTLCache[str, bool] = TTLCache(maxsize=1, ttl=30)
search_cache: TTLCache[str, list[BookSummary]] = TTLCache(maxsize=100, ttl=300)
details_cache: TTLCache[str, BookDetails] = TTLCache(maxsize=100, ttl=300)
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
    return random.choice(USER_AGENTS)  # nosec B311 # noqa: S311


def get_trackers() -> list[str]:
    """Load trackers from configuration and optional local JSON file.

    Uses TTLCache to avoid repeated I/O while allowing config updates to propagate.
    """
    with CACHE_LOCK:
        if "default" in tracker_cache:
            return tracker_cache["default"]

    env_trackers = current_app.config.get("MAGNET_TRACKERS", [])
    if env_trackers:
        result = cast(list[str], env_trackers)
        with CACHE_LOCK:
            tracker_cache["default"] = result
        return result

    try:
        base_dir = Path(__file__).resolve().parents[2]
        json_path = base_dir / "trackers.json"

        if json_path.exists():
            with open(json_path, encoding="utf-8") as f:
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

    with CACHE_LOCK:
        tracker_cache["default"] = DEFAULT_TRACKERS
    return DEFAULT_TRACKERS


def get_mirrors() -> list[str]:
    """Retrieve the list of mirrors to attempt, in priority order."""
    primary = current_app.config.get("ABB_HOSTNAME", "audiobookbay.lu")
    extra = current_app.config.get("ABB_MIRRORS", [])
    candidates = [primary] + extra + DEFAULT_MIRRORS
    return list(dict.fromkeys(candidates))


def get_session() -> Session:
    """Configure and return a requests Session with retry logic."""
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
    """Configure and return a reusable requests Session with ZERO retries for availability checks.

    Reuses a single session instance to prevent expensive SSL context recreation overhead
    during high-concurrency mirror checks.

    Returns:
        Session: A configured requests Session object with 0 retries.
    """
    global _ping_session
    if _ping_session is None:
        with _ping_session_lock:
            if _ping_session is None:
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
                _ping_session = session

    return _ping_session


def get_thread_session() -> Session:
    """Retrieve or create a thread-local Session."""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = get_session()
    return cast(Session, _thread_local.session)


def get_headers(user_agent: str | None = None, referer: str | None = None) -> dict[str, str]:
    """Generate standard HTTP headers for scraping requests."""
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

    Uses a zero-retry reusable session to fail fast.
    """
    url = f"https://{hostname}/"
    headers = get_headers()
    session = get_ping_session()

    try:
        response = session.head(url, headers=headers, timeout=5, allow_redirects=True)
        if response.status_code == 200:  # noqa: PLR2004
            return hostname
    except (requests.Timeout, requests.ConnectionError):
        # FAIL FAST: If HEAD times out, do NOT try GET.
        return None
    except requests.RequestException:
        pass

    try:
        response = session.get(url, headers=headers, timeout=5, stream=True)
        response.close()
        if response.status_code == 200:  # noqa: PLR2004
            return hostname
    except (requests.Timeout, requests.RequestException):
        pass

    return None


def find_best_mirror() -> str | None:
    """Find the first reachable AudiobookBay mirror using concurrent checks."""
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

    mirrors = get_mirrors()
    logger.debug(f"Checking connectivity for {len(mirrors)} mirrors...")
    safe_mirror_workers = 5

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=safe_mirror_workers)
    futures = [executor.submit(check_mirror, host) for host in mirrors]

    try:
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                logger.info(f"Found active mirror: {result}")
                for f in futures:
                    f.cancel()
                with CACHE_LOCK:
                    mirror_cache[cache_key] = result
                return result
    finally:
        executor.shutdown(wait=False)

    logger.error("No working AudiobookBay mirrors found! Caching failure for 30s.")
    with CACHE_LOCK:
        failure_cache["failure"] = True
    return None
