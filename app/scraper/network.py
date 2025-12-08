"""Network module handling HTTP sessions, proxies, and mirrors."""

import concurrent.futures
import json
import logging
import os
import random
import threading
from functools import lru_cache
from typing import cast

import requests
from cachetools import TTLCache
from flask import current_app
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util.retry import Retry

from app.constants import DEFAULT_MIRRORS, DEFAULT_TRACKERS, USER_AGENTS
from app.scraper.parser import BookDict

logger = logging.getLogger(__name__)

# --- Concurrency Control ---
# Caps concurrent scrapes at 3 to prevent anti-bot triggers.
MAX_CONCURRENT_REQUESTS = 3
GLOBAL_REQUEST_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

# --- Caches ---
# Explicit type parameters for TTLCache to satisfy strict MyPy
mirror_cache: TTLCache[str, str | None] = TTLCache(maxsize=1, ttl=600)
search_cache: TTLCache[str, list[BookDict]] = TTLCache(maxsize=100, ttl=300)
details_cache: TTLCache[str, BookDict] = TTLCache(maxsize=100, ttl=300)


def get_random_user_agent() -> str:
    """Return a random User-Agent string from the constants list."""
    return random.choice(USER_AGENTS)  # nosec B311


@lru_cache(maxsize=1)
def get_trackers() -> list[str]:
    """Load trackers from configuration and optional local JSON file.

    Lazy-loaded and cached to avoid repeated I/O.
    Prioritizes:
    1. Environment Variable (via Config)
    2. trackers.json (Volume Mount)
    3. Internal Defaults

    Returns:
        list[str]: A list of tracker URLs.
    """
    # 1. Configured via Env/Config
    # We must access current_app inside the function (request time), not at module level
    env_trackers = current_app.config.get("MAGNET_TRACKERS", [])
    if env_trackers:
        return cast(list[str], env_trackers)

    # 2. Volume Mount Override
    json_path = os.path.join(os.getcwd(), "trackers.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    logger.info("Loaded custom trackers from trackers.json")
                    return cast(list[str], data)
                else:
                    logger.warning("trackers.json contains invalid data (expected a list). Using defaults.")
        except Exception as e:
            logger.warning(f"Failed to load trackers.json: {e}", exc_info=True)

    # 3. Defaults
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

    Args:
        hostname: The domain name to check (e.g., "audiobookbay.lu").

    Returns:
        str | None: The hostname if reachable, otherwise None.
    """
    url = f"https://{hostname}/"
    headers = get_headers()

    try:
        response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return hostname
    except (requests.Timeout, requests.RequestException):
        pass

    try:
        response = requests.get(url, headers=headers, timeout=5, stream=True)
        response.close()
        if response.status_code == 200:
            return hostname
    except (requests.Timeout, requests.RequestException):
        pass

    return None


def find_best_mirror() -> str | None:
    """Find the first reachable AudiobookBay mirror from the configured list.

    Uses threaded checks for speed and caches the result manually to ensure
    failed attempts (None) are not cached.

    Returns:
        str | None: The hostname of the active mirror, or None if all fail.
    """
    # Manual caching check using a static key since this function is parameterless
    cache_key = "active_mirror"
    if cache_key in mirror_cache:
        return mirror_cache[cache_key]

    # Dynamic retrieval of mirrors list
    mirrors = get_mirrors()

    logger.debug(f"Checking connectivity for {len(mirrors)} mirrors...")
    safe_mirror_workers = 5

    with concurrent.futures.ThreadPoolExecutor(max_workers=safe_mirror_workers) as executor:
        future_to_host = {executor.submit(check_mirror, host): host for host in mirrors}
        for future in concurrent.futures.as_completed(future_to_host):
            result = future.result()
            if result:
                logger.info(f"Found active mirror: {result}")
                # CACHE UPDATE: Only cache successful results
                mirror_cache[cache_key] = result
                return result

    logger.error("No working AudiobookBay mirrors found!")
    # Do not cache None
    return None
