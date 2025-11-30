import concurrent.futures
import logging
import os
import random
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from cachetools import TTLCache, cached

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
    "audiobookbay.pl",
]
ABB_FALLBACK_HOSTNAMES = list(dict.fromkeys(ABB_FALLBACK_HOSTNAMES))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
]

trackers_env = os.getenv("MAGNET_TRACKERS")
if trackers_env:
    DEFAULT_TRACKERS = [t.strip() for t in trackers_env.split(",") if t.strip()]
else:
    DEFAULT_TRACKERS = [
        "udp://tracker.openbittorrent.com:80",
        "udp://opentor.org:2710",
        "udp://tracker.ccc.de:80",
        "udp://tracker.blackunicorn.xyz:6969",
        "udp://tracker.coppersurfer.tk:6969",
        "udp://tracker.leechers-paradise.org:6969",
    ]


def check_mirror(hostname):
    url = f"https://{hostname}/"
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return hostname
    except (requests.Timeout, requests.RequestException):
        pass
    return None


@cached(cache=TTLCache(maxsize=1, ttl=600))
def find_best_mirror():
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
    sleep_time = random.uniform(1.0, 3.0)
    logger.debug(f"Jitter: Sleeping {sleep_time:.2f}s before fetching page {page}...")
    time.sleep(sleep_time)

    headers = {"User-Agent": random.choice(USER_AGENTS)}
    page_results = []
    base_url = f"https://{hostname}"
    url = f"{base_url}/page/{page}/"
    params = {"s": query}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
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
                # Robust URL handling: Handles both relative (/abss/...) and absolute (https://...) links
                link = urljoin(base_url, title_element["href"])

                # Refined selector for cover image
                cover_img = post.select_one(".postContent img")
                if cover_img and cover_img.has_attr("src"):
                    cover = urljoin(base_url, cover_img["src"])
                else:
                    cover = "/static/images/default_cover.jpg"

                post_info = post.select_one(".postInfo")
                post_info_text = post_info.get_text(separator=" ", strip=True) if post_info else ""

                language = "N/A"
                if post_info_text:
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
                        match = re.search(r"Posted:\s*([^<]+)", details_html)
                        if match:
                            post_date = match.group(1).strip()
                    except Exception:
                        pass

                    try:
                        match = re.search(r"Format:\s*<span[^>]*>([^<]+)</span>", details_html)
                        if match:
                            book_format = match.group(1).strip()
                    except Exception:
                        pass

                    try:
                        match = re.search(r"Bitrate:\s*<span[^>]*>([^<]+)</span>", details_html)
                        if match:
                            bitrate = match.group(1).strip()
                    except Exception:
                        pass

                    try:
                        match = re.search(r"File Size:\s*<span[^>]*>([^<]+)</span>\s*([^<]+)", details_html)
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

    return page_results


@cached(cache=TTLCache(maxsize=32, ttl=3600))
def search_audiobookbay(query, max_pages=PAGE_LIMIT):
    active_hostname = find_best_mirror()
    if not active_hostname:
        logger.error("Could not connect to any AudiobookBay mirrors.")
        return []

    logger.info(f"Searching for '{query}' on active mirror: https://{active_hostname}...")
    results = []
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
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.get(details_url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Failed to fetch details page. Status Code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        info_hash = None

        info_hash_row = soup.find("td", string=re.compile(r"Info Hash", re.IGNORECASE))
        if info_hash_row:
            sibling = info_hash_row.find_next_sibling("td")
            if sibling:
                info_hash = sibling.text.strip()

        if not info_hash:
            logger.debug("Info Hash table cell not found. Attempting regex fallback...")
            hash_match = re.search(r"\b([a-fA-F0-9]{40})\b", response.text)
            if hash_match:
                info_hash = hash_match.group(1)

        if not info_hash:
            logger.error("Info Hash could not be found on the page.")
            return None

        tracker_rows = soup.find_all("td", string=re.compile(r"udp://|http://", re.IGNORECASE))
        trackers = [row.text.strip() for row in tracker_rows]

        if DEFAULT_TRACKERS:
            trackers.extend(DEFAULT_TRACKERS)

        trackers = list(dict.fromkeys(trackers))
        trackers_query = "&".join(f"tr={requests.utils.quote(tracker)}" for tracker in trackers)
        magnet_link = f"magnet:?xt=urn:btih:{info_hash}&{trackers_query}"

        return magnet_link

    except Exception as e:
        logger.error(f"Failed to extract magnet link: {e}")
        return None
