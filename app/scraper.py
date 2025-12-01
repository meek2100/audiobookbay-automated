import concurrent.futures
import json
import logging
import os
import random
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from cachetools import TTLCache, cached
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Configuration
PAGE_LIMIT = int(os.getenv("PAGE_LIMIT", "3"))
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
extra_mirrors = os.getenv("ABB_MIRRORS_LIST", "")
if extra_mirrors:
    ABB_FALLBACK_HOSTNAMES.extend([m.strip() for m in extra_mirrors.split(",") if m.strip()])

ABB_FALLBACK_HOSTNAMES = list(dict.fromkeys(ABB_FALLBACK_HOSTNAMES))

# Fallback User Agents if fake_useragent fails
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

# Initialize UserAgent object with fallback protection
try:
    ua_generator: UserAgent | None = UserAgent(fallback=FALLBACK_USER_AGENTS[0])
except Exception:
    logger.warning("Failed to initialize fake_useragent, using hardcoded list.")
    ua_generator = None


# --- OPTIMIZATION: Pre-compile Regex Patterns ---
# Improved: Captures text until the next HTML tag start, making it order-independent
RE_LANGUAGE = re.compile(r"Language:\s*([^<]+)", re.IGNORECASE)
RE_POSTED = re.compile(r"Posted:\s*([^<]+)")
RE_FORMAT = re.compile(r"Format:\s*<span[^>]*>([^<]+)</span>")
RE_BITRATE = re.compile(r"Bitrate:\s*<span[^>]*>([^<]+)</span>")
RE_FILESIZE = re.compile(r"File Size:\s*<span[^>]*>([^<]+)</span>\s*([^<]+)")
RE_INFO_HASH = re.compile(r"Info Hash", re.IGNORECASE)
RE_HASH_STRING = re.compile(r"\b([a-fA-F0-9]{40})\b")
RE_TRACKERS = re.compile(r"udp://|http://", re.IGNORECASE)


def get_random_user_agent() -> str:
    """Returns a random user agent from fake_useragent or the fallback list."""
    if ua_generator:
        try:
            return str(ua_generator.random)
        except Exception:
            pass
    return random.choice(FALLBACK_USER_AGENTS)


def load_trackers() -> list[str]:
    """Loads trackers from env var, local JSON, or defaults."""
    trackers_env = os.getenv("MAGNET_TRACKERS")
    if trackers_env:
        return [t.strip() for t in trackers_env.split(",") if t.strip()]

    json_path = os.path.join(os.path.dirname(__file__), "trackers.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data  # type: ignore
        except Exception as e:
            logger.warning(f"Failed to load trackers.json: {e}")

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
    """
    Generates HTTP headers for scraping requests.

    Args:
        user_agent: The User-Agent string to use (if None, a random one is generated).
        referer: The HTTP Referer header value.

    Returns:
        A dictionary of HTTP headers.
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
    """
    Checks if a specific mirror hostname is reachable.

    Args:
        hostname: The domain name to check.

    Returns:
        The hostname if reachable, else None.
    """
    url = f"https://{hostname}/"
    session = get_session()
    try:
        response = session.head(url, headers=get_headers(), timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return hostname
    except (requests.Timeout, requests.RequestException):
        pass
    return None


# ROBUSTNESS: Explicitly typed TTLCache (requires cachetools 5+)
mirror_cache: TTLCache = TTLCache(maxsize=1, ttl=600)

# OPTIMIZATION: Cache search results for 5 minutes.
search_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


@cached(cache=mirror_cache)
def find_best_mirror() -> str | None:
    """
    Finds the first reachable AudiobookBay mirror from the list.

    Returns:
        The hostname of the working mirror, or None if all fail.
    """
    logger.debug("Checking connectivity for all mirrors...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ABB_FALLBACK_HOSTNAMES)) as executor:
        future_to_host = {executor.submit(check_mirror, host): host for host in ABB_FALLBACK_HOSTNAMES}
        for future in concurrent.futures.as_completed(future_to_host):
            result = future.result()
            if result:
                logger.info(f"Found active mirror: {result}")
                return result
    logger.error("No working AudiobookBay mirrors found!")
    return None


def fetch_and_parse_page(
    session: Session, hostname: str, query: str, page: int, user_agent: str
) -> list[dict[str, Any]]:
    """
    Fetches a single search result page and parses it.

    Args:
        session: Active requests Session.
        hostname: The mirror hostname.
        query: The search query.
        page: Page number.
        user_agent: UA string to use.

    Returns:
        A list of dictionaries containing book details.
    """
    sleep_time = random.uniform(1.0, 3.0)
    time.sleep(sleep_time)

    base_url = f"https://{hostname}"
    url = f"{base_url}/page/{page}/"
    params = {"s": query}
    referer = base_url if page == 1 else f"{base_url}/page/{page - 1}/?s={query}"
    headers = get_headers(user_agent, referer)

    page_results = []

    try:
        response = session.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        posts = soup.select(".post")

        if not posts:
            logger.debug(f"No posts found on page {page}")
            return []

        for post in posts:
            try:
                title_element = post.select_one(".postTitle > h2 > a")
                if not title_element:
                    continue

                title = title_element.text.strip()
                link = urljoin(base_url, str(title_element["href"]))

                cover_img = post.select_one(".postContent img")
                if cover_img and cover_img.has_attr("src"):
                    cover = urljoin(base_url, str(cover_img["src"]))
                else:
                    cover = "/static/images/default_cover.jpg"

                post_info = post.select_one(".postInfo")
                language = "N/A"
                if post_info:
                    # Robustness: Use the raw HTML string for the regex so 'RE_LANGUAGE'
                    # can correctly match until the next '<' character (start of a tag).
                    # This makes it independent of the field order.
                    try:
                        language_match = RE_LANGUAGE.search(str(post_info))
                        if language_match:
                            language = language_match.group(1).strip()
                    except Exception:
                        pass

                details_paragraph = post.select_one(".postContent p[style*='text-align:center']")
                post_date, book_format, bitrate, file_size = "N/A", "N/A", "N/A", "N/A"

                if details_paragraph:
                    details_html = str(details_paragraph)
                    try:
                        match = RE_POSTED.search(details_html)
                        if match:
                            post_date = match.group(1).strip()
                    except Exception:
                        pass
                    try:
                        match = RE_FORMAT.search(details_html)
                        if match:
                            book_format = match.group(1).strip()
                    except Exception:
                        pass
                    try:
                        match = RE_BITRATE.search(details_html)
                        if match:
                            bitrate = match.group(1).strip()
                    except Exception:
                        pass
                    try:
                        match = RE_FILESIZE.search(details_html)
                        if match:
                            file_size = f"{match.group(1).strip()} {match.group(2).strip()}"
                    except Exception:
                        pass

                page_results.append(
                    {
                        "title": title,
                        "link": link,
                        "cover": cover,
                        "language": language,
                        "post_date": post_date,
                        "format": book_format,
                        "bitrate": bitrate,
                        "file_size": file_size,
                    }
                )
            except Exception as e:
                logger.error(f"Could not process a post on page {page}. Details: {e}")
                continue

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch page {page}. Reason: {e}")
        raise e

    return page_results


@cached(cache=search_cache)
def search_audiobookbay(query: str, max_pages: int = PAGE_LIMIT) -> list[dict[str, Any]]:
    """
    Searches AudiobookBay for the given query across multiple pages in parallel.
    Results are cached for performance.
    """
    active_hostname = find_best_mirror()
    if not active_hostname:
        logger.error("Could not connect to any AudiobookBay mirrors.")
        raise ConnectionError("No reachable AudiobookBay mirrors found.")

    logger.info(f"Searching for '{query}' on active mirror: https://{active_hostname}...")
    results = []

    session_user_agent = get_random_user_agent()
    session = get_session()

    safe_workers = min(max_pages, 5)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=safe_workers) as executor:
            future_to_page = {
                executor.submit(fetch_and_parse_page, session, active_hostname, query, page, session_user_agent): page
                for page in range(1, max_pages + 1)
            }
            for future in concurrent.futures.as_completed(future_to_page):
                try:
                    page_data = future.result()
                    results.extend(page_data)
                except Exception as exc:
                    logger.error(f"Page scrape failed, invalidating mirror cache. Details: {exc}")
                    mirror_cache.clear()
                    # Also clear search cache if we hit a network or logic error
                    search_cache.clear()
    finally:
        session.close()

    return results


def extract_magnet_link(details_url: str) -> tuple[str | None, str | None]:
    """
    Scrapes the details page to find the info hash and generates a magnet link.

    Returns:
        A tuple of (magnet_link, error_message).
    """
    if not details_url:
        return None, "No URL provided."

    try:
        parsed = urlparse(details_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None, "Invalid URL scheme."
    except Exception:
        return None, "Malformed URL."

    session = get_session()
    headers = get_headers(referer=details_url)

    try:
        response = session.get(details_url, headers=headers, timeout=15)
        if response.status_code != 200:
            msg = f"Failed to fetch details page. Status Code: {response.status_code}"
            logger.error(msg)
            return None, msg

        soup = BeautifulSoup(response.text, "html.parser")
        info_hash = None

        info_hash_row = soup.find("td", string=RE_INFO_HASH)
        if info_hash_row:
            sibling = info_hash_row.find_next_sibling("td")
            if sibling:
                info_hash = sibling.text.strip()

        if not info_hash:
            logger.debug("Info Hash table cell not found. Attempting regex fallback...")
            hash_match = RE_HASH_STRING.search(response.text)
            if hash_match:
                info_hash = hash_match.group(1)

        if not info_hash:
            msg = "Info Hash could not be found on the page."
            logger.error(msg)
            return None, msg

        tracker_rows = soup.find_all("td", string=RE_TRACKERS)
        trackers = [row.text.strip() for row in tracker_rows]

        if DEFAULT_TRACKERS:
            trackers.extend(DEFAULT_TRACKERS)

        trackers = list(dict.fromkeys(trackers))
        trackers_query = "&".join(f"tr={requests.utils.quote(tracker)}" for tracker in trackers)
        magnet_link = f"magnet:?xt=urn:btih:{info_hash}&{trackers_query}"

        return magnet_link, None

    except Exception as e:
        logger.error(f"Failed to extract magnet link: {e}")
        return None, str(e)
    finally:
        logger.debug("Closing scraper session")
        session.close()
