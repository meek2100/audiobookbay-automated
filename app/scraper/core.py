import concurrent.futures
import logging
import random
import re
import time
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.sessions import Session

from .network import (
    ABB_FALLBACK_HOSTNAMES,
    DEFAULT_TRACKERS,
    GLOBAL_REQUEST_SEMAPHORE,
    PAGE_LIMIT,
    find_best_mirror,
    get_headers,
    get_random_user_agent,
    get_session,
    mirror_cache,
    search_cache,
)
from .parser import RE_HASH_STRING, RE_INFO_HASH, RE_TRACKERS, get_text_after_label

logger = logging.getLogger(__name__)


def fetch_and_parse_page(
    session: Session, hostname: str, query: str, page: int, user_agent: str
) -> list[dict[str, Any]]:
    """
    Fetches a single search result page and parses it into a list of books.
    Enforces a global semaphore to limit concurrent scraping requests.

    Args:
        session: The active requests Session.
        hostname: The AudiobookBay mirror to scrape.
        query: The search term.
        page: The page number to fetch.
        user_agent: The User-Agent string to use for the request.

    Returns:
        list[dict[str, Any]]: A list of dictionaries, each representing a book found on the page.
    """
    base_url = f"https://{hostname}"
    url = f"{base_url}/page/{page}/"
    params = {"s": query}
    referer = base_url if page == 1 else f"{base_url}/page/{page - 1}/?s={query}"
    headers = get_headers(user_agent, referer)

    page_results = []

    try:
        with GLOBAL_REQUEST_SEMAPHORE:
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

                language = "N/A"
                category = "N/A"
                post_info = post.select_one(".postInfo")
                if post_info:
                    info_text = post_info.get_text(" ", strip=True)
                    lang_match = re.search(r"Language:\s*(\w+)", info_text)
                    if lang_match:
                        language = lang_match.group(1)
                    cat_match = re.search(r"Category:\s*(.+?)(?:\s+Language:|$)", info_text)
                    if cat_match:
                        category = cat_match.group(1).strip()

                details_paragraph = None
                content_div = post.select_one(".postContent")
                if content_div:
                    for p in content_div.find_all("p"):
                        if "Posted:" in p.get_text():
                            details_paragraph = p
                            break

                post_date, book_format, bitrate, file_size = "N/A", "N/A", "N/A", "N/A"

                if details_paragraph:
                    post_date = get_text_after_label(details_paragraph, "Posted:")
                    book_format = get_text_after_label(details_paragraph, "Format:")
                    bitrate = get_text_after_label(details_paragraph, "Bitrate:")
                    file_size = get_text_after_label(details_paragraph, "File Size:")

                if bitrate == "?":
                    bitrate = "Unknown"

                page_results.append(
                    {
                        "title": title,
                        "link": link,
                        "cover": cover,
                        "language": language,
                        "category": category,
                        "post_date": post_date,
                        "format": book_format,
                        "bitrate": bitrate,
                        "file_size": file_size,
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


def search_audiobookbay(query: str, max_pages: int = PAGE_LIMIT) -> list[dict[str, Any]]:
    """
    Searches AudiobookBay for the given query using cached search results if available.
    Manages thread pool for parallel page fetching.

    Args:
        query: The search string.
        max_pages: Maximum number of pages to scrape (default: configured limit).

    Returns:
        list[dict[str, Any]]: A list of book dictionaries found across all pages.

    Raises:
        ConnectionError: If no mirrors are reachable.
    """
    if query in search_cache:
        return search_cache[query]

    active_hostname = find_best_mirror()
    if not active_hostname:
        logger.error("Could not connect to any AudiobookBay mirrors.")
        raise ConnectionError("No reachable AudiobookBay mirrors found.")

    logger.info(f"Searching for '{query}' on active mirror: https://{active_hostname}...")
    results = []

    session_user_agent = get_random_user_agent()
    session = get_session()
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


def get_book_details(details_url: str) -> dict[str, Any]:
    """
    Scrapes the specific book details page to retrieve metadata, description, and hash.
    Validates the URL to prevent SSRF.

    Args:
        details_url: The full URL of the book page on AudiobookBay.

    Returns:
        dict[str, Any]: A dictionary containing detailed book metadata.

    Raises:
        ValueError: If the URL is invalid or not from an allowed domain.
    """
    if details_url in search_cache:
        return search_cache[details_url]

    if not details_url:
        raise ValueError("No URL provided.")

    try:
        parsed_url = urlparse(details_url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {str(e)}") from e

    if parsed_url.netloc not in ABB_FALLBACK_HOSTNAMES:
        logger.warning(f"Blocked SSRF attempt to: {details_url}")
        raise ValueError(f"Invalid domain: {parsed_url.netloc}. Only AudiobookBay mirrors are allowed.")

    session = get_session()
    headers = get_headers(referer=details_url)

    try:
        with GLOBAL_REQUEST_SEMAPHORE:
            time.sleep(random.uniform(1.0, 2.0))
            response = session.get(details_url, headers=headers, timeout=15)

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        title = "Unknown Title"
        title_tag = soup.select_one(".postTitle h1")
        if title_tag:
            title = title_tag.get_text(strip=True)

        cover = "/static/images/default_cover.jpg"
        cover_tag = soup.select_one('.postContent img[itemprop="image"]')
        if cover_tag and cover_tag.has_attr("src"):
            cover = urljoin(details_url, str(cover_tag["src"]))

        # --- Metadata Parsing (Language & Category) ---
        language = "N/A"
        category = "N/A"
        post_info = soup.select_one(".postInfo")
        if post_info:
            info_text = post_info.get_text(" ", strip=True)
            # Language
            lang_match = re.search(r"Language:\s*(\w+)", info_text)
            if lang_match:
                language = lang_match.group(1)
            # FIX: Added Category parsing (matches fetch_and_parse_page logic)
            cat_match = re.search(r"Category:\s*(.+?)(?:\s+Language:|$)", info_text)
            if cat_match:
                category = cat_match.group(1).strip()

        # --- Content Parsing (Format, Bitrate, Posted Date) ---
        book_format = "N/A"
        bitrate = "N/A"
        post_date = "N/A"

        content_div = soup.select_one(".postContent")
        if content_div:
            # We iterate through paragraphs to find metadata labels
            for p in content_div.find_all("p"):
                p_text = p.get_text()
                if "Format:" in p_text:
                    book_format = get_text_after_label(p, "Format:")
                if "Bitrate:" in p_text:
                    bitrate = get_text_after_label(p, "Bitrate:")
                # FIX: Added Posted Date parsing
                if "Posted:" in p_text:
                    post_date = get_text_after_label(p, "Posted:")

        if bitrate == "?":
            bitrate = "Unknown"

        author = "Unknown"
        narrator = "Unknown"
        author_tag = soup.select_one('span.author[itemprop="author"]')
        if author_tag:
            author = author_tag.get_text(strip=True)
        narrator_tag = soup.select_one('span.narrator[itemprop="author"]')
        if narrator_tag:
            narrator = narrator_tag.get_text(strip=True)

        description = "No description available."
        desc_tag = soup.select_one("div.desc")
        if desc_tag:
            # SECURITY FIX: Strict HTML Sanitization to prevent XSS in "Privacy Proxy" mode.
            # We only allow basic formatting tags. Scripts, iframes, styles, and events are stripped.
            allowed_tags = ["p", "br", "b", "i", "em", "strong", "ul", "li"]

            for tag in desc_tag.find_all(True):
                if tag.name not in allowed_tags:
                    # Remove the tag wrapper but keep its text content
                    tag.unwrap()
                else:
                    # Clear all attributes (e.g., onclick, style, class) from allowed tags
                    tag.attrs = {}

            description = desc_tag.decode_contents()

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

        result = {
            "title": title,
            "cover": cover,
            "description": description,
            "trackers": trackers,
            "file_size": file_size,
            "info_hash": info_hash,
            "link": details_url,
            "language": language,
            "category": category,  # FIX: Added category
            "post_date": post_date,  # FIX: Added post_date
            "format": book_format,
            "bitrate": bitrate,
            "author": author,
            "narrator": narrator,
        }
        search_cache[details_url] = result
        return result

    except Exception as e:
        logger.error(f"Failed to fetch book details: {e}", exc_info=True)
        raise e
    finally:
        session.close()


def extract_magnet_link(details_url: str) -> tuple[str | None, str | None]:
    """
    Scrapes the details page to find the info hash and generates a magnet link.

    Args:
        details_url: The URL of the book page.

    Returns:
        tuple[str | None, str | None]: A tuple containing (magnet_link, error_message).
                                       If successful, error_message is None.
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
        with GLOBAL_REQUEST_SEMAPHORE:
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
        trackers.extend(DEFAULT_TRACKERS)
        trackers = list(dict.fromkeys(trackers))

        trackers_query = "&".join(f"tr={quote(tracker)}" for tracker in trackers)
        magnet_link = f"magnet:?xt=urn:btih:{info_hash}&{trackers_query}"

        return magnet_link, None

    except Exception as e:
        logger.error(f"Failed to extract magnet link: {e}", exc_info=True)
        return None, str(e)
    finally:
        session.close()
