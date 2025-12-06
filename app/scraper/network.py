"""Network module handling HTTP sessions, proxies, and mirrors."""

import concurrent.futures
import json
import logging
import os
import random
import threading
from typing import cast

import requests
from cachetools import TTLCache, cached
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util.retry import Retry

from app.constants import DEFAULT_MIRRORS, DEFAULT_TRACKERS, USER_AGENTS

logger = logging.getLogger(__name__)

# --- Configuration ---
try:
    PAGE_LIMIT = int(os.getenv("PAGE_LIMIT", "3").strip())
except ValueError:
    logger.warning("Invalid PAGE_LIMIT in environment. Defaulting to 3.")
    PAGE_LIMIT = 3

DEFAULT_HOSTNAME = os.getenv("ABB_HOSTNAME", "audiobookbay.lu").strip(" \"'")

# Start with user preferred hostname, then defaults
ABB_FALLBACK_HOSTNAMES: list[str] = [DEFAULT_HOSTNAME] + DEFAULT_MIRRORS

# Allow users to add mirrors via env var
extra_mirrors = os.getenv("ABB_MIRRORS", "")
if extra_mirrors:
    ABB_FALLBACK_HOSTNAMES.extend([m.strip() for m in extra_mirrors.split(",") if m.strip()])

# OPTIMIZATION: Deduplicate mirrors while preserving the original order.
# Order matters because we want to prioritize the user-defined hostname and reliable mirrors first.
ABB_FALLBACK_HOSTNAMES = list(dict.fromkeys(ABB_FALLBACK_HOSTNAMES))

# --- Concurrency Control ---
# OPTIMIZATION: Increased from 2 to 3.
# Since the default PAGE_LIMIT is 3, a limit of 2 forces the 3rd page to wait
# for one of the first two to finish (serialization), doubling the search time.
MAX_CONCURRENT_REQUESTS = 3
GLOBAL_REQUEST_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

# --- Caches ---
mirror_cache: TTLCache = TTLCache(maxsize=1, ttl=600)
search_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


def get_random_user_agent() -> str:
    """Returns a random User-Agent string from the constants list."""
    return random.choice(USER_AGENTS)  # nosec B311


def load_trackers() -> list[str]:
    """Load trackers from environment variable, local JSON, or internal defaults.

    Returns:
        list[str]: A list of tracker URLs.
    """
    trackers_env = os.getenv("MAGNET_TRACKERS")
    if trackers_env:
        return [t.strip() for t in trackers_env.split(",") if t.strip()]

    # FIX: Look for trackers.json in the current working directory (container root)
    # rather than inside the package structure.
    json_path = os.path.join(os.getcwd(), "trackers.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return cast(list[str], data)
                else:
                    logger.warning("trackers.json contains invalid data (expected a list). Using defaults.")
        except Exception as e:
            logger.warning(f"Failed to load trackers.json: {e}", exc_info=True)

    return DEFAULT_TRACKERS


# This is called at module level to initialize the list
CONFIGURED_TRACKERS = load_trackers()


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


@cached(cache=mirror_cache)  # type: ignore[untyped-decorator]
def find_best_mirror() -> str | None:
    """Find the first reachable AudiobookBay mirror from the configured list.

    Uses threaded checks for speed and caches the result.

    Returns:
        str | None: The hostname of the active mirror, or None if all fail.
    """
    logger.debug("Checking connectivity for all mirrors...")
    safe_mirror_workers = 5

    with concurrent.futures.ThreadPoolExecutor(max_workers=safe_mirror_workers) as executor:
        future_to_host = {executor.submit(check_mirror, host): host for host in ABB_FALLBACK_HOSTNAMES}
        for future in concurrent.futures.as_completed(future_to_host):
            result = future.result()
            if result:
                logger.info(f"Found active mirror: {result}")
                return result
    logger.error("No working AudiobookBay mirrors found!")
    return None
