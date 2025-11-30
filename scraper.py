import os
import re
import requests
import concurrent.futures
import logging
import time
import random
from bs4 import BeautifulSoup
from cachetools import cached, TTLCache

logger = logging.getLogger(__name__)

# Configuration
PAGE_LIMIT = int(os.getenv("PAGE_LIMIT", 3))
DEFAULT_HOSTNAME = os.getenv("ABB_HOSTNAME", "audiobookbay.lu").strip(" \"'")

ABB_FALLBACK_HOSTNAMES = [
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
    "audiobookbay.pl"
]
# Deduplicate preserving order
ABB_FALLBACK_HOSTNAMES = list(dict.fromkeys(ABB_FALLBACK_HOSTNAMES))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/114.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/113.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/114.0.1823.67",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15"
]

DEFAULT_TRACKERS = [
    "udp://tracker.openbittorrent.com:80",
    "udp://opentor.org:2710",
    "udp://tracker.ccc.de:80",
    "udp://tracker.blackunicorn.xyz:6969",
    "udp://tracker.coppersurfer.tk:6969",
    "udp://tracker.leechers-paradise.org:6969",
]

def check_mirror(hostname):
    """
    Checks if a specific hostname is reachable via a HEAD request.

    Args:
        hostname (str): The hostname to check (e.g., 'audiobookbay.is').

    Returns:
        str: The hostname if it is reachable (HTTP 200).
        None: If the hostname is unreachable or errors occur.
    """
    url = f"https://{hostname}/"
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        # Use HEAD request for speed
        response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return hostname
    except Exception:
        pass
    return None

@cached(cache=TTLCache(maxsize=1, ttl=600))
def find_best_mirror():
    """
    Finds the fastest working AudiobookBay mirror.

    Returns:
        str: The hostname of the best mirror.
        None: If no mirrors are found.
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

def fetch_and_parse_page(hostname, query, page):
    """
    Fetches and parses a single page of results from the specified hostname.

    Args:
        hostname (str): The AudiobookBay hostname.
        query (str): The search query.
        page (int): The page number to fetch.

    Returns:
        list: A list of dictionaries, where each dict represents a book found.
    """
    # Anti-Ban Measure: Jitter
    sleep_time = random.uniform(1.0, 3.0)
    logger.debug(f"Jitter: Sleeping {sleep_time:.2f}s before fetching page {page}...")
    time.sleep(sleep_time)

    headers = {"User-Agent": random.choice(USER_AGENTS)}
    page_results = []
    url = f"https://{hostname}/page/{page}/?s={query.replace(' ', '+')}"

    try:
        response = requests.get(url, headers=headers, timeout=15)
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
                link = f"https://{hostname}{title_element['href']}"

                cover_url = post.select_one("img")["src"] if post.select_one("img") else None
                cover = cover_url if cover_url else "/static/images/default_cover.jpg"

                post_info = post.select_one(".postInfo")
                post_info_text = post_info.get_text(separator=" ", strip=True) if post_info else ""

                language = "N/A"
                try:
                    language_match = re.search(r"Language:\s*(.*?)(?:\s*Keywords:|$)", post_info_text, re.DOTALL)
                    if language_match:
                        language = language_match.group(1).strip()
                except Exception:
                    pass

                details_paragraph = post.select_one(".postContent p[style*='text-align:center']")
                post_date, book_format, bitrate, file_size = "N/A", "N/A", "N/A", "N/A"

                if details_paragraph:
                    details_html = str(details_paragraph)

                    try:
                        post_date_match = re.search(r"Posted:\s*([^<]+)", details_html)
                        if post_date_match: post_date = post_date_match.group(1).strip()
                    except Exception: pass

                    try:
                        format_match = re.search(r"Format:\s*<span[^>]*>([^<]+)</span>", details_html)
                        if format_match: book_format = format_match.group(1).strip()
                    except Exception: pass

                    try:
                        bitrate_match = re.search(r"Bitrate:\s*<span[^>]*>([^<]+)</span>", details_html)
                        if bitrate_match: bitrate = bitrate_match.group(1).strip()
                    except Exception: pass

                    try:
                        file_size_match = re.search(r"File Size:\s*<span[^>]*>([^<]+)</span>\s*([^<]+)", details_html)
                        if file_size_match:
                            file_size = f"{file_size_match.group(1).strip()} {file_size_match.group(2).strip()}"
                    except Exception: pass

                page_results.append({
                    "title": title,
                    "link": link,
                    "cover": cover,
                    "language": language,
                    "post_date": post_date,
                    "format": book_format,
                    "bitrate": bitrate,
                    "file_size": file_size,
                })
            except Exception as e:
                logger.error(f"Could not process a post on page {page}. Details: {e}")
                continue

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch page {page}. Reason: {e}")

    return page_results

@cached(cache=TTLCache(maxsize=32, ttl=3600))
def search_audiobookbay(query, max_pages=PAGE_LIMIT):
    """
    Searches AudiobookBay using cached mirror and parallel requests.
    """
    active_hostname = find_best_mirror()
    if not active_hostname:
        raise Exception("Could not connect to any AudiobookBay mirrors.")

    logger.info(f"Searching for '{query}' on active mirror: https://{active_hostname}...")
    results = []

    # Anti-Ban Measure: Limit concurrency to 2
    safe_workers = min(max_pages, 2)

    with concurrent.futures.ThreadPoolExecutor(max_workers=safe_workers) as executor:
        future_to_page = {
            executor.submit(fetch_and_parse_page, active_hostname, query, page): page
            for page in range(1, max_pages + 1)
        }
        for future in concurrent.futures.as_completed(future_to_page):
            try:
                page_data = future.result()
                results.extend(page_data)
            except Exception as exc:
                logger.error(f"Page generated an exception: {exc}")

    return results

def extract_magnet_link(details_url):
    """
    Extracts the magnet link from a specific book details page.
    """
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.get(details_url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Failed to fetch details page. Status Code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        info_hash_row = soup.find("td", string=re.compile(r"Info Hash", re.IGNORECASE))
        if not info_hash_row:
            logger.error("Info Hash not found on the page.")
            return None
        info_hash = info_hash_row.find_next_sibling("td").text.strip()

        tracker_rows = soup.find_all("td", string=re.compile(r"udp://|http://", re.IGNORECASE))
        trackers = [row.text.strip() for row in tracker_rows]

        if not trackers:
            logger.warning("No trackers found on the page. Using default trackers.")
            trackers = DEFAULT_TRACKERS

        trackers_query = "&".join(f"tr={requests.utils.quote(tracker)}" for tracker in trackers)
        magnet_link = f"magnet:?xt=urn:btih:{info_hash}&{trackers_query}"

        logger.debug(f"Generated Magnet Link: {magnet_link}")
        return magnet_link

    except Exception as e:
        logger.error(f"Failed to extract magnet link: {e}")
        return None