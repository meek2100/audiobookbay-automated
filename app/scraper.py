import concurrent.futures
import json
import logging
import os
import random
import re
import threading
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from cachetools import TTLCache, cached
from requests.adapters import HTTPAdapter
from requests.sessions import Session
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Configuration
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
# RENAME: Changed from ABB_MIRRORS_LIST to ABB_MIRRORS
extra_mirrors = os.getenv("ABB_MIRRORS", "")
if extra_mirrors:
    # Robustly handle trailing commas or empty strings in the list
    ABB_FALLBACK_HOSTNAMES.extend([m.strip() for m in extra_mirrors.split(",") if m.strip()])

ABB_FALLBACK_HOSTNAMES = list(dict.fromkeys(ABB_FALLBACK_HOSTNAMES))

# Robust User Agent list (No external dependency to prevent hangs)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]

# GLOBAL CONCURRENCY CONTROL
# We use a semaphore to limit the TOTAL number of simultaneous requests to ABB.
# This prevents the app from hammering the server if the user mass-clicks "Download"
# or if multiple search threads fire at once.
# 2 Concurrent requests is a safe "Human-like" limit.
MAX_CONCURRENT_REQUESTS = 2
GLOBAL_REQUEST_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

# --- Regex Patterns ---
# Only keeping regexes for unstructured text (Magnet links) or fallback
RE_INFO_HASH = re.compile(r"Info Hash", re.IGNORECASE)
RE_HASH_STRING = re.compile(r"\b([a-fA-F0-9]{40})\b")
RE_TRACKERS = re.compile(r".*(?:udp|http)://.*", re.IGNORECASE)


def get_random_user_agent() -> str:
    """Returns a random user agent from the hardcoded list."""
    return random.choice(USER_AGENTS)


def load_trackers() -> list[str]:
    """
    Loads trackers from env var, local JSON, or defaults.
    Note: trackers.json is an OPTIONAL user-provided override file.
    """
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
    """
    Generates HTTP headers for scraping requests.
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
    Performs a HEAD request to the mirror to validate reachability without downloading content.
    """
    url = f"https://{hostname}/"

    # OPTIMIZATION: Use a direct request instead of get_session().
    # get_session() has 5 retries, which causes massive delays (90s+) when checking dead mirrors.
    # We want to fail FAST here.
    try:
        response = requests.head(url, headers=get_headers(), timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return hostname
    except (requests.Timeout, requests.RequestException):
        # We expect many failures here, so we pass silently to try the next mirror
        pass
    return None


mirror_cache: TTLCache = TTLCache(maxsize=1, ttl=600)
search_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


@cached(cache=mirror_cache)
def find_best_mirror() -> str | None:
    """Finds the first reachable AudiobookBay mirror from the list."""
    logger.debug("Checking connectivity for all mirrors...")

    # Limit concurrent checks to 5 to avoid a massive burst of connection attempts (DDoS protection)
    # This might slow down startup slightly if many mirrors are dead, but it's safer.
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


def _get_text_after_label(container: Tag, label_text: str) -> str:
    """
    Robustly finds values based on a label within a BS4 container.
    Logic: Find the text node containing 'label_text', then look at its
    siblings to find the value. Checks next sibling element (span)
    or parses the current text node for the label.
    """
    try:
        # Find the text string (e.g., "Format:")
        label_node = container.find(string=re.compile(label_text))
        if not label_node:
            return "N/A"

        # Strategy 1: The value is in the next sibling element (e.g., <span>MP3</span>)
        next_elem = label_node.find_next_sibling()
        if next_elem and next_elem.name == "span":
            val = next_elem.get_text(strip=True)
            # Special handling for File Size which might have unit in next text node
            if "File Size" in label_text:
                unit_node = next_elem.next_sibling
                if unit_node and isinstance(unit_node, str):
                    val += f" {unit_node.strip()}"
            return val

        # Strategy 2: The value is in the same text node (e.g., "Posted: 30 Nov 2025")
        # Split by the label and take the rest
        if ":" in label_node:
            parts = label_node.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()

        return "N/A"
    except Exception:
        return "N/A"


def fetch_and_parse_page(
    session: Session, hostname: str, query: str, page: int, user_agent: str
) -> list[dict[str, Any]]:
    """
    Fetches a single search result page and parses it using BS4 navigation.
    """
    base_url = f"https://{hostname}"
    url = f"{base_url}/page/{page}/"
    params = {"s": query}
    referer = base_url if page == 1 else f"{base_url}/page/{page - 1}/?s={query}"
    headers = get_headers(user_agent, referer)

    page_results = []

    try:
        # CONCURRENCY CONTROL: Wait for a slot in the global semaphore
        with GLOBAL_REQUEST_SEMAPHORE:
            # JITTER: Sleep for 1-3 seconds to mimic human reading speed/network latency
            # This is critical for avoiding bot detection.
            sleep_time = random.uniform(1.0, 3.0)
            time.sleep(sleep_time)

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

                # --- Robust Parsing Logic ---
                language = "N/A"
                post_info = post.select_one(".postInfo")
                if post_info:
                    # Language is usually a text node like "Language: English"
                    # We iterate text parts to find it
                    info_text = post_info.get_text(" ", strip=True)
                    # Regex on the cleaned text content is safer than HTML regex
                    lang_match = re.search(r"Language:\s*(\w+)", info_text)
                    if lang_match:
                        language = lang_match.group(1)

                # ROBUSTNESS FIX: iterate through paragraphs to find the metadata block
                # rather than relying on brittle CSS selectors like "p[style*='text-align:center']"
                details_paragraph = None
                content_div = post.select_one(".postContent")
                if content_div:
                    for p in content_div.find_all("p"):
                        if "Posted:" in p.get_text():
                            details_paragraph = p
                            break

                post_date, book_format, bitrate, file_size = "N/A", "N/A", "N/A", "N/A"

                if details_paragraph:
                    post_date = _get_text_after_label(details_paragraph, "Posted:")
                    book_format = _get_text_after_label(details_paragraph, "Format:")
                    bitrate = _get_text_after_label(details_paragraph, "Bitrate:")
                    file_size = _get_text_after_label(details_paragraph, "File Size:")

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
                # Capture a truncated snippet of the failed HTML element for debugging
                html_snippet = str(post)[:500].replace("\n", " ")
                logger.error(f"Could not process a post on page {page}. Error: {e}. HTML Snippet: {html_snippet}")
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

    # Cap worker threads to 3 to align with the Global Semaphore and prevent thread starvation
    safe_workers = min(max_pages, 3)

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
                    logger.error(f"Page scrape failed, invalidating mirror cache. Details: {exc}", exc_info=True)
                    mirror_cache.clear()
                    search_cache.clear()
    finally:
        session.close()

    logger.info(f"Search for '{query}' completed. Found {len(results)} results.")
    return results


def get_book_details(details_url: str) -> dict[str, Any]:
    """
    Scrapes the specific book details page to allow viewing content safely via the server.
    """
    if not details_url:
        raise ValueError("No URL provided.")

    # --- SECURITY: SSRF Protection ---
    try:
        parsed_url = urlparse(details_url)
        # Check against our allowed list of hosts.
        # Using a separate try/except here avoids the B904 issue because we aren't
        # catching an exception during the check, we are validating.
        if parsed_url.netloc not in ABB_FALLBACK_HOSTNAMES:
            logger.warning(f"Blocked SSRF attempt to: {details_url}")
            raise ValueError(f"Invalid domain: {parsed_url.netloc}. Only AudiobookBay mirrors are allowed.")
    except ValueError:
        # Re-raise ValueErrors (like the one we just raised) as-is
        raise
    except Exception as e:
        # Catch parsing errors (malformed URLs) and chain them
        raise ValueError(f"Invalid URL format: {str(e)}") from e
    # ---------------------------------

    session = get_session()
    headers = get_headers(referer=details_url)

    try:
        with GLOBAL_REQUEST_SEMAPHORE:
            time.sleep(random.uniform(1.0, 2.0))  # Jitter
            response = session.get(details_url, headers=headers, timeout=15)

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # --- Extract Metadata ---
        title = "Unknown Title"
        title_tag = soup.select_one(".postTitle h1")
        if title_tag:
            title = title_tag.get_text(strip=True)

        cover = "/static/images/default_cover.jpg"
        cover_tag = soup.select_one('.postContent img[itemprop="image"]')
        if cover_tag and cover_tag.has_attr("src"):
            cover = urljoin(details_url, str(cover_tag["src"]))

        # Description
        description = "No description available."
        desc_tag = soup.select_one("div.desc")
        if desc_tag:
            # Clean up links in description to avoid users leaving the safe environment
            for a in desc_tag.find_all("a"):
                a.replace_with(a.get_text())
            description = desc_tag.decode_contents()

        # Trackers & File Info
        trackers = []
        file_size = "N/A"
        info_hash = "N/A"

        info_table = soup.select_one("table.torrent_info")
        if info_table:
            for row in info_table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)

                    if "Tracker:" in label or "Announce URL:" in label:
                        trackers.append(value)
                    elif "File Size:" in label:
                        file_size = value
                    elif "Info Hash:" in label:
                        info_hash = value

        return {
            "title": title,
            "cover": cover,
            "description": description,
            "trackers": trackers,
            "file_size": file_size,
            "info_hash": info_hash,
            "link": details_url,
        }

    except Exception as e:
        logger.error(f"Failed to fetch book details: {e}", exc_info=True)
        raise e
    finally:
        session.close()


def extract_magnet_link(details_url: str) -> tuple[str | None, str | None]:
    """
    Scrapes the details page to find the info hash and generates a magnet link.
    Constructs the magnet link using the info hash and configured trackers.
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
        # CONCURRENCY CONTROL: Wait for a slot in the global semaphore
        # This protects the server if multiple "Downloads" are queued quickly.
        with GLOBAL_REQUEST_SEMAPHORE:
            # JITTER: Sleep for 1-3 seconds to mimic human reading speed.
            time.sleep(random.uniform(1.0, 3.0))

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

        logger.debug(f"Extracted magnet link: {magnet_link[:60]}... (truncated)")
        return magnet_link, None

    except Exception as e:
        logger.error(f"Failed to extract magnet link: {e}", exc_info=True)
        return None, str(e)
    finally:
        logger.debug("Closing scraper session")
        session.close()
