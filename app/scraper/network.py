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

logger = logging.getLogger(__name__)

# --- Configuration ---
try:
    PAGE_LIMIT = int(os.getenv("PAGE_LIMIT", "3").strip())
except ValueError:
    logger.warning("Invalid PAGE_LIMIT in environment. Defaulting to 3.")
    PAGE_LIMIT = 3

DEFAULT_HOSTNAME = os.getenv("ABB_HOSTNAME", "audiobookbay.lu").strip(" \"'")

ABB_FALLBACK_HOSTNAMES: list[str] = [
    DEFAULT_HOSTNAME,
    "audiobookbay.is",
    "audiobookbay.se",
    "audiobookbay.li",
    "audiobookbay.ws",
    "audiobookbay.la",
    "audiobookbay.me",
    "audiobookbay.fi",
    "theaudiobookbay.com",
    "audiobookbay.nl",
    "audiobookbay.pl",
]

# Allow users to add mirrors via env var
extra_mirrors = os.getenv("ABB_MIRRORS", "")
if extra_mirrors:
    ABB_FALLBACK_HOSTNAMES.extend([m.strip() for m in extra_mirrors.split(",") if m.strip()])

ABB_FALLBACK_HOSTNAMES = list(dict.fromkeys(ABB_FALLBACK_HOSTNAMES))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# --- Concurrency Control ---
MAX_CONCURRENT_REQUESTS = 2
GLOBAL_REQUEST_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

# --- Caches ---
mirror_cache: TTLCache = TTLCache(maxsize=1, ttl=600)
search_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def load_trackers() -> list[str]:
    """Loads trackers from env var, local JSON, or defaults."""
    trackers_env = os.getenv("MAGNET_TRACKERS")
    if trackers_env:
        return [t.strip() for t in trackers_env.split(",") if t.strip()]

    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trackers.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return cast(list[str], data)
        except Exception as e:
            logger.warning(f"Failed to load trackers.json: {e}", exc_info=True)

    return [
        "udp://tracker.openbittorrent.com:80",
        "udp://opentor.org:2710",
        "udp://tracker.ccc.de:80",
        "udp://tracker.blackunicorn.xyz:6969",
        "udp://tracker.coppersurfer.tk:6969",
        "udp://tracker.leechers-paradise.org:6969",
    ]


DEFAULT_TRACKERS = load_trackers()


def get_session() -> Session:
    """Configures and returns a requests Session with retry logic."""
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
    """Checks if a mirror is reachable via HEAD or GET."""
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


@cached(cache=mirror_cache)
def find_best_mirror() -> str | None:
    """Finds the first reachable AudiobookBay mirror from the list."""
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
