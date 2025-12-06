"""Core scraping logic for AudiobookBay."""

import concurrent.futures
import logging
import random
import time
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import current_app
from requests.sessions import Session

from app.constants import DEFAULT_COVER_FILENAME
from app.scraper.network import (
    GLOBAL_REQUEST_SEMAPHORE,
    details_cache,
    find_best_mirror,
    get_headers,
    get_mirrors,
    get_random_user_agent,
    get_session,
    get_trackers,
    mirror_cache,
    search_cache,
)
from app.scraper.parser import (
    RE_HASH_STRING,
    RE_INFO_HASH,
    BookDict,
    parse_post_content,
)

logger = logging.getLogger(__name__)


def fetch_and_parse_page(session: Session, hostname: str, query: str, page: int, user_agent: str) -> list[BookDict]:
    """Fetch a single search result page and parse it into a list of books.

    Enforces a global semaphore to limit concurrent scraping requests.

    Args:
        session: The active requests Session.
        hostname: The AudiobookBay mirror to scrape.
        query: The search term.
        page: The page number to fetch.
        user_agent: The User-Agent string to use for the request.

    Returns:
        list[BookDict]: A list of dictionaries, each representing a book found on the page.
    """
    base_url = f"https://{hostname}"
    url = f"{base_url}/page/{page}/"
    params = {"s": query}
    referer = base_url if page == 1 else f"{base_url}/page/{page - 1}/?s={query}"
    headers = get_headers(user_agent, referer)

    page_results: list[BookDict] = []

    try:
        with GLOBAL_REQUEST_SEMAPHORE:
            # Random jitter (0.5-1.5s) to prevent IP bans.
            sleep_time = random.uniform(0.5, 1.5)  # nosec B311
            time.sleep(sleep_time)
            # 30s timeout for better resilience on slow connections/proxies.
            response = session.get(url, params=params, headers=headers, timeout=30)

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
                cover = None  # Default to None so UI handles versioned default
                if cover_img and cover_img.has_attr("src"):
                    extracted_cover = urljoin(base_url, str(cover_img["src"]))
                    # If remote is default, keep as None to use local versioned default.
                    if not extracted_cover.endswith(DEFAULT_COVER_FILENAME):
                        cover = extracted_cover

                post_info = post.select_one(".postInfo")
                content_div = post.select_one(".postContent")
                meta = parse_post_content(content_div, post_info)

                page_results.append(
                    {
                        "title": title,
                        "link": link,
                        "cover": cover,
                        "language": meta.language,
                        "category": meta.category,
                        "post_date": meta.post_date,
                        "format": meta.format,
                        "bitrate": meta.bitrate,
                        "file_size": meta.file_size,
                    }
                )
            except Exception as e:
                html_snippet = str(post)[:500].replace("\n", " ")
                logger.error(f"Could not process post. Error: {e}. Snippet: {html_snippet}")
                continue

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch page {page}. Reason: {e}")
        raise e

    return page_results


def search_audiobookbay(query: str, max_pages: int | None = None) -> list[BookDict]:
    """Search AudiobookBay for the given query using cached search results if available.

    Manages thread pool for parallel page fetching.

    Args:
        query: The search string.
        max_pages: Maximum number of pages to scrape. If None, uses configured limit.

    Returns:
        list[BookDict]: A list of book dictionaries found across all pages.

    Raises:
        ConnectionError: If no mirrors are reachable.
    """
    if query in search_cache:
        cached_result: list[BookDict] = search_cache[query]
        return cached_result

    # Load configuration dynamically
    if max_pages is None:
        max_pages = current_app.config.get("PAGE_LIMIT", 3)

    active_hostname = find_best_mirror()
    if not active_hostname:
        logger.error("Could not connect to any AudiobookBay mirrors.")
        raise ConnectionError("No reachable AudiobookBay mirrors found.")

    logger.info(f"Searching for '{query}' on active mirror: https://{active_hostname}...")
    results: list[BookDict] = []

    session_user_agent = get_random_user_agent()
    session = get_session()

    # Cap workers to avoid excessive threads
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
                    logger.error(f"Page scrape failed, invalidating mirror cache. {exc}", exc_info=True)
                    mirror_cache.clear()
    finally:
        session.close()

    logger.info(f"Search for '{query}' completed. Found {len(results)} results.")
    search_cache[query] = results
    return results


def get_book_details(details_url: str) -> BookDict:
    """Scrape the specific book details page to retrieve metadata, description, and hash.

    Validates the URL to prevent SSRF.

    Args:
        details_url: The full URL of the book page on AudiobookBay.

    Returns:
        BookDict: A dictionary containing detailed book metadata.

    Raises:
        ValueError: If the URL is invalid or not from an allowed domain.
    """
    if details_url in details_cache:
        cached_result: BookDict = details_cache[details_url]
        return cached_result

    if not details_url:
        raise ValueError("No URL provided.")

    try:
        parsed_url = urlparse(details_url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {str(e)}") from e

    # Retrieve valid mirrors dynamically for SSRF check
    allowed_hosts = get_mirrors()
    if parsed_url.netloc not in allowed_hosts:
        logger.warning(f"Blocked SSRF attempt to: {details_url}")
        raise ValueError(f"Invalid domain: {parsed_url.netloc}. Only AudiobookBay mirrors are allowed.")

    session = get_session()
    headers = get_headers(referer=details_url)

    try:
        with GLOBAL_REQUEST_SEMAPHORE:
            # Random jitter (0.5-1.5s) to prevent IP bans.
            time.sleep(random.uniform(0.5, 1.5))  # nosec B311
            # 30s timeout for better resilience.
            response = session.get(details_url, headers=headers, timeout=30)

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title = "Unknown Title"
        title_tag = soup.select_one(".postTitle h1")
        if title_tag:
            title = title_tag.get_text(strip=True)

        cover = None
        cover_tag = soup.select_one('.postContent img[itemprop="image"]')
        if cover_tag and cover_tag.has_attr("src"):
            extracted_cover = urljoin(details_url, str(cover_tag["src"]))
            if not extracted_cover.endswith(DEFAULT_COVER_FILENAME):
                cover = extracted_cover

        post_info = soup.select_one(".postInfo")
        content_div = soup.select_one(".postContent")
        meta = parse_post_content(content_div, post_info)

        author = "Unknown"
        narrator = "Unknown"
        author_tag = soup.select_one('span.author[itemprop="author"]')
        if author_tag:
            author = author_tag.get_text(strip=True)
        narrator_tag = soup.select_one('span.narrator[itemprop="author"]')
        if narrator_tag:
            narrator = narrator_tag.get_text(strip=True)

        if author == "?":
            author = "Unknown"
        if narrator == "?":
            narrator = "Unknown"

        description = "No description available."
        desc_tag = soup.select_one("div.desc")
        if desc_tag:
            # Strict HTML Sanitization
            allowed_tags = ["p", "br", "b", "i", "em", "strong", "ul", "li"]

            for tag in desc_tag.find_all(True):
                if tag.name not in allowed_tags:
                    tag.unwrap()
                else:
                    tag.attrs = {}

            description = desc_tag.decode_contents()

        trackers = []
        file_size = meta.file_size
        info_hash = "Unknown"

        # --- INFO HASH & TRACKER EXTRACTION ---
        info_table = soup.select_one("table.torrent_info")
        if info_table:
            for row in info_table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if "Tracker:" in label or "Announce URL:" in label:
                        trackers.append(value)
                    elif "File Size:" in label and file_size == "Unknown":
                        file_size = value
                    elif "Info Hash:" in label:
                        info_hash = value

        if info_hash == "Unknown":
            info_hash_row = soup.find("td", string=RE_INFO_HASH)
            if info_hash_row:
                sibling = info_hash_row.find_next_sibling("td")
                if sibling:
                    info_hash = sibling.text.strip()

        if info_hash == "Unknown":
            hash_match = RE_HASH_STRING.search(response.text)
            if hash_match:
                info_hash = hash_match.group(1)

        if file_size == "?":
            file_size = "Unknown"

        result: BookDict = {
            "title": title,
            "cover": cover,
            "description": description,
            "trackers": trackers,
            "file_size": file_size,
            "info_hash": info_hash,
            "link": details_url,
            "language": meta.language,
            "category": meta.category,
            "post_date": meta.post_date,
            "format": meta.format,
            "bitrate": meta.bitrate,
            "author": author,
            "narrator": narrator,
        }
        details_cache[details_url] = result
        return result

    except Exception as e:
        logger.error(f"Failed to fetch book details: {e}", exc_info=True)
        raise e
    finally:
        session.close()


def extract_magnet_link(details_url: str) -> tuple[str | None, str | None]:
    """Generate a magnet link by retrieving book details.

    Uses 'get_book_details' to ensure unified parsing logic, caching, and security.

    Args:
        details_url: The URL of the book page.

    Returns:
        tuple[str | None, str | None]: A tuple containing (magnet_link, error_message).
                                       If successful, error_message is None.
    """
    try:
        details = get_book_details(details_url)

        info_hash = details.get("info_hash")
        if not info_hash or info_hash == "Unknown":
            return None, "Info Hash could not be found on the page."

        trackers = details.get("trackers", [])
        if trackers is None:
            trackers = []

        # Load additional trackers lazy (IO or Config access)
        extra_trackers = get_trackers()
        trackers.extend(extra_trackers)

        safe_trackers: list[str] = [str(t) for t in trackers]
        safe_trackers = list(dict.fromkeys(safe_trackers))

        trackers_query = "&".join(f"tr={quote(tracker)}" for tracker in safe_trackers)
        magnet_link = f"magnet:?xt=urn:btih:{info_hash}&{trackers_query}"

        return magnet_link, None

    except ValueError as e:
        return None, str(e)
    except Exception as e:
        logger.error(f"Failed to extract magnet link: {e}", exc_info=True)
        return None, str(e)
