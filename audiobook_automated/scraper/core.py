# File: audiobook_automated/scraper/core.py
"""Core scraping logic for AudiobookBay."""

import concurrent.futures
import logging
import random
import time
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import current_app

from audiobook_automated.constants import ERROR_HASH_NOT_FOUND
from audiobook_automated.extensions import executor
from audiobook_automated.scraper.network import (
    CACHE_LOCK,
    details_cache,
    find_best_mirror,
    get_headers,
    get_mirrors,
    get_random_user_agent,
    get_semaphore,
    get_thread_session,
    get_trackers,
    mirror_cache,
    search_cache,
)
from audiobook_automated.scraper.parser import (
    BookDetails,
    BookSummary,
    normalize_cover_url,
    parse_book_details,
    parse_post_content,
)

logger = logging.getLogger(__name__)


def fetch_and_parse_page(  # noqa: PLR0915
    hostname: str, query: str, page: int, user_agent: str, timeout: int
) -> list[BookSummary]:
    """Fetch a single search result page and parse it into a list of books.

    Enforces a global semaphore to limit concurrent scraping requests.
    Uses a thread-local session to reuse TCP connections.

    Args:
        hostname: The AudiobookBay mirror to scrape.
        query: The search term.
        page: The page number to fetch.
        user_agent: The User-Agent string to use for the request.
        timeout: The request timeout in seconds.

    Returns:
        list[BookSummary]: A list of dictionaries, each representing a book found on the page.
    """
    base_url = f"https://{hostname}"

    # FIX: Always use the explicit paginated URL structure.
    # Previously, page 1 used f"{base_url}/" which caused results to be empty
    # due to inconsistencies in how the site handles the root search URL vs /page/X/.
    url = f"{base_url}/page/{page}/"

    params = {"s": query}
    referer = base_url if page == 1 else f"{base_url}/page/{page - 1}/?s={query}"
    headers = get_headers(user_agent, referer)

    page_results: list[BookSummary] = []

    # PERFORMANCE: Use thread-local session to reuse connections across pages
    session = get_thread_session()
    # SECURITY: Clear cookies to prevent state leakage between unrelated requests
    session.cookies.clear()

    try:
        # OPTIMIZATION: Sleep outside the semaphore.
        # Sleeping while holding the semaphore blocks other threads from doing useful work.
        # Random jitter (0.5-1.5s) to prevent IP bans.
        sleep_time = random.uniform(0.5, 1.5)  # nosec B311  # noqa: S311
        time.sleep(sleep_time)

        # Semaphore is now retrieved dynamically
        with get_semaphore():
            response = session.get(url, params=params, headers=headers, timeout=timeout)

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        posts = soup.select(".post")

        if not posts:
            logger.debug(f"No posts found on page {page}")
            return []

        for post in posts:
            try:
                title_element = post.select_one(".postTitle > h2 > a")
                if not title_element:
                    continue

                # Safety: Check for href existence to avoid KeyError crashes
                href = title_element.get("href")
                if not href:
                    logger.warning("Post title element missing href attribute. Skipping.")
                    continue

                title = title_element.text.strip()
                link = urljoin(base_url, str(href))

                cover_img = post.select_one(".postContent img")
                cover = None
                if cover_img and cover_img.has_attr("src"):
                    # Use centralized helper for consistent normalization
                    cover = normalize_cover_url(base_url, str(cover_img["src"]))

                post_info = post.select_one(".postInfo")
                content_div = post.select_one(".postContent")

                # GUARD: Skip posts with missing content
                if not content_div:
                    logger.warning(f"Post missing content: {title}. Skipping.")
                    continue

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
    except Exception as e:
        logger.error(f"Unexpected error fetching page {page}: {e}")
        raise RuntimeError(f"Unexpected error fetching page {page}") from e
    # NOTE: Do NOT close session here; it is thread-local and reused.

    return page_results


def search_audiobookbay(query: str, max_pages: int | None = None) -> list[BookSummary]:  # noqa: PLR0912
    """Search AudiobookBay for the given query using cached search results if available.

    Uses a shared global thread pool for parallel page fetching to reduce overhead.

    Args:
        query: The search string.
        max_pages: Maximum number of pages to scrape. If None, uses configured limit.
                   This parameter is part of the cache key to prevent collision between
                   shallow and deep searches.

    Returns:
        list[BookSummary]: A list of book dictionaries found across all pages.

    Raises:
        ConnectionError: If no mirrors are reachable.
    """
    # Load configuration dynamically
    if max_pages is None:
        # FIX: Force integer cast to prevent 'Operator + not supported for None' pyright error
        # in the range() loop below, even though 'None' is impossible here.
        max_pages = int(current_app.config.get("PAGE_LIMIT", 3))

    # Core Task 5: Use optimized cache key format
    # Using ::page_{max_pages} allows distinguishing between different pagination limits for the same query
    cache_key = f"{query}::page_{max_pages}"

    # SAFETY: Wrap cache read in lock for thread safety
    with CACHE_LOCK:
        if cache_key in search_cache:
            cached_result: list[BookSummary] = search_cache[cache_key]
            return cached_result

    active_hostname = find_best_mirror()
    if not active_hostname:
        # UX IMPROVEMENT: Error message now explicitly mentions backoff/negative caching.
        logger.error("Could not connect to any AudiobookBay mirrors (or backoff active).")
        raise ConnectionError("No reachable AudiobookBay mirrors found (or system is in backoff cooldown).")

    logger.info(f"Searching for '{query}' on active mirror: https://{active_hostname}...")
    results: list[BookSummary] = []

    session_user_agent = get_random_user_agent()

    # Retrieve configured timeout to pass to the worker threads
    # (Threads cannot access current_app reliably)
    timeout = current_app.config.get("SCRAPER_TIMEOUT", 30)

    try:
        # Use the global executor to avoid spinning up new threads per request
        futures: list[concurrent.futures.Future[list[BookSummary]]] = []
        for page in range(1, max_pages + 1):
            futures.append(
                executor.submit(
                    fetch_and_parse_page,
                    active_hostname,
                    query,
                    page,
                    session_user_agent,
                    timeout,
                )
            )

        # RESILIENCE: Local flag to prevent cache thrashing.
        # If multiple pages fail, we only invalidate the mirror once per search request.
        mirror_invalidated = False
        seen_links: set[str] = set()

        # PROCESSING FIX: Iterate futures in order to handle pagination correctly.
        # Previously using as_completed() caused a race condition where an empty result
        # from a fast (but later) page would cancel earlier pages that were still loading.
        for i, future in enumerate(futures):
            try:
                page_data = future.result()
                if not page_data:
                    # OPTIMIZATION: Stop pagination if a page returns 0 results
                    # This prevents fetching deeper pages when results are exhausted.
                    logger.debug(f"Page {i + 1} returned 0 results. Stopping pagination.")
                    # Cancel only remaining futures (pages > i+1) to save resources
                    for f in futures[i + 1 :]:
                        f.cancel()
                    break

                # Deduplication logic to handle shifting results
                for book in page_data:
                    if book["link"] not in seen_links:
                        results.append(book)
                        seen_links.add(book["link"])
            except (requests.ConnectionError, requests.Timeout) as exc:
                logger.error(f"Network error during scrape on page {i + 1}: {exc}")
                # FAIL-FAST: Cancel all pending requests immediately
                for f in futures[i + 1 :]:
                    f.cancel()

                # Only clear cache once per search loop to prevent lock contention/thrashing
                if not mirror_invalidated:
                    logger.warning(f"Invalidating mirror cache due to network failure: {active_hostname}")
                    with CACHE_LOCK:
                        mirror_cache.clear()
                    mirror_invalidated = True

                # Stop processing further pages
                break
            except Exception as exc:
                logger.error(f"Page scrape failed (Parsing/Generic): {exc}", exc_info=True)
                # Do not invalidate mirror for parsing errors or other non-connection issues

    finally:
        pass

    logger.info(f"Search for '{query}' completed. Found {len(results)} results.")

    with CACHE_LOCK:
        search_cache[cache_key] = results

    return results


def get_book_details(details_url: str) -> BookDetails:
    """Scrape the specific book details page to retrieve metadata, description, and hash.

    Validates the URL to prevent SSRF.

    Args:
        details_url: The full URL of the book page on AudiobookBay.

    Returns:
        BookDetails: A dictionary containing detailed book metadata.

    Raises:
        ValueError: If the URL is invalid or not from an allowed domain.
    """
    if details_url in details_cache:
        cached_result: BookDetails = details_cache[details_url]
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

    # PERFORMANCE: Use thread-local session
    session = get_thread_session()
    headers = get_headers(referer=details_url)

    # Retrieve configured timeout or default to 30
    timeout = current_app.config.get("SCRAPER_TIMEOUT", 30)

    try:
        # COMPLIANCE: Jitter sleep is retained to strictly comply with AGENTS.md Rule 0.
        # "Do NOT remove or reduce jitter sleeps... before all external requests."
        time.sleep(random.uniform(0.5, 1.5))  # nosec B311  # noqa: S311

        with get_semaphore():
            # 30s timeout for better resilience.
            response = session.get(details_url, headers=headers, timeout=timeout)

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        # DELEGATION: Parsing logic moved to parser.py
        result = parse_book_details(soup, details_url)

        details_cache[details_url] = result
        return result

    except Exception as e:
        logger.error(f"Failed to fetch book details: {e}", exc_info=True)
        raise RuntimeError(f"Failed to fetch book details: {e}") from e
    # NOTE: Do NOT close session here; it is thread-local and reused.


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
            return None, ERROR_HASH_NOT_FOUND

        # Simplify retrieval; .get() defaults to None if key missing, so 'or []' ensures list
        trackers = details.get("trackers") or []

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
