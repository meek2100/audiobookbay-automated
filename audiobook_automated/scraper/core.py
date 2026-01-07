# File: audiobook_automated/scraper/core.py
"""Core scraper logic for retrieving search results and details."""

import logging
import random
import time
from typing import Any

from . import network, parser

logger = logging.getLogger(__name__)

# Used to synchronize access to the details cache across threads
CACHE_LOCK: Any = network.threading.Lock()


def get_search_url(base_url: str, query: str | None, page: int = 1) -> str:
    """Construct the search URL for a given query and page number."""
    # Explicitly handle pagination in the URL format
    # The source site uses /page/N/?s=query for search results
    if query:
        return f"{base_url}/page/{page}/?s={query}"
    # Browse mode (no query) also uses /page/N/
    return f"{base_url}/page/{page}/"


def search_audiobookbay(query: str, max_pages: int = 5) -> list[dict[str, Any]]:
    """Search AudiobookBay for the given query across multiple pages.

    Args:
        query: Search term (e.g. "Harry Potter")
        max_pages: Maximum number of pages to scrape (default: 5)

    Returns:
        A list of dictionaries containing book summaries.
    """
    logger.info("Search: Starting search for '%s' (Limit: %d pages)", query, max_pages)

    # 1. Find a working mirror
    base_url = network.find_best_mirror()
    if not base_url:
        logger.error("Search: No working mirror found. Aborting.")
        return []

    # Check Cache
    cache_key = f"{query}::page_{max_pages}"
    with network.CACHE_LOCK:
        if cache_key in network.search_cache:
            logger.debug("Search: Cache hit for '%s'", cache_key)
            return network.search_cache[cache_key]

    results: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    # Create a queue to hold futures (async tasks)
    futures = []

    # Use Executor from extensions (passed via current_app if needed, or import)
    # However, since this function runs in a request context or background task,
    # we need to be careful. The current implementation uses the global executor.
    from ..extensions import executor

    # Submit tasks for each page
    # We use a loop to submit tasks, but we need to handle the fact that
    # the site might have fewer pages than max_pages.
    # To optimize, we could fetch page 1 first, check total pages, then fetch the rest.
    # For now, we will submit all and handle empty results gracefully.

    # Loop through pages 1 to max_pages
    for page in range(1, max_pages + 1):
        url = get_search_url(base_url, query, page)
        future = executor.submit(fetch_page_results, url)
        futures.append(future)

    # Collect results as they complete
    # Note: We don't guarantee order here, but search results are usually sorted by the site.
    # If order matters strictly, we should map futures to page numbers.
    for future in futures:
        try:
            page_results = future.result()
            if not page_results:
                # If a page returns no results, it likely means we hit the end of the results.
                # Optimization - Cancel remaining futures?
                # For simplicity, we just ignore empty results.
                continue

            for item in page_results:
                link = item.get("link")
                if link and link not in seen_links:
                    seen_links.add(link)
                    results.append(item)

        except network.requests.HTTPError as e:
            logger.error(f"Search: HTTP Error (5xx/4xx) from mirror: {e}. Invalidating mirror.")
            with network.CACHE_LOCK:
                if "active_mirror" in network.mirror_cache:
                    del network.mirror_cache["active_mirror"]
        except Exception:
            logger.exception("Search: Error processing page result.")

    logger.info("Search: Completed. Found %d unique results.", len(results))

    # Update Cache
    with network.CACHE_LOCK:
        network.search_cache[cache_key] = results

    return results


def fetch_page_results(url: str) -> list[dict[str, Any]]:
    """Fetch and parse a single search results page.

    Args:
        url: The full URL to fetch.

    Returns:
        A list of book summary dictionaries.
    """
    # Compliance: Rate limiting and concurrency control (Rule 0)
    with network.get_semaphore():
        time.sleep(random.uniform(0.5, 1.5))  # Jitter
        try:
            session = network.get_session()
            response = session.get(url, timeout=10)
            response.raise_for_status()

            soup = parser.parse_html(response.text)
            return parser.parse_search_results(soup, url)

        except (network.requests.ConnectionError, network.requests.Timeout):
            # Do not expose raw URL in logs if it contains sensitive info (unlikely here)
            logger.warning("Search: Connection error fetching page: %s", url)
            return []
        except network.requests.HTTPError:
            # Re-raise HTTP errors (4xx/5xx) to allow search_audiobookbay to handle invalidation
            raise
        except Exception:
            # Catch-all for parsing errors
            logger.exception("Search: Unexpected error fetching page: %s", url)
            return []


def get_book_details(url: str, refresh: bool = False) -> dict[str, Any] | None:
    """Fetch detailed information for a specific book.

    Args:
        url: The URL of the book page.
        refresh: If True, bypass the cache and re-fetch.

    Returns:
        A dictionary containing book details, or None if fetching fails.
    """
    # 1. Check Cache
    if not refresh:
        with CACHE_LOCK:
            if url in network.details_cache:
                logger.debug("Details: Cache hit for %s", url)
                return network.details_cache[url]

    logger.info("Details: Fetching %s", url)

    # SSRF Protection: Ensure URL belongs to allowed domains
    from urllib.parse import urlparse

    domain = urlparse(url).netloc
    allowed_mirrors = network.get_mirrors()
    if domain not in allowed_mirrors:
        logger.warning("Details: Blocked SSRF attempt to %s", url)
        # Raising ValueError as expected by security tests
        raise ValueError(f"Invalid domain: {domain}")

    try:
        # 2. Fetch Page
        # Ensure we have a valid session with headers (User-Agent)
        session = network.get_session()
        response = session.get(url, timeout=15)
        response.raise_for_status()

        # 3. Parse Content
        soup = parser.parse_html(response.text)
        book_details = parser.parse_book_details(soup, url)

        # 4. Update Cache
        if book_details:
            with CACHE_LOCK:
                network.details_cache[url] = book_details
            return book_details

    except Exception as e:
        logger.error("Details: Failed to fetch details for %s: %s", url, e)

    return None


def extract_magnet_link(url: str) -> tuple[str | None, str | None]:
    """Extract and construct the magnet link from the book details page.

    Args:
        url: The URL of the book details page.

    Returns:
        tuple: (magnet_link, error_message). Both are None on success, or (None, error) on failure.
    """
    try:
        details = get_book_details(url)
        if not details:
            return None, "Failed to retrieve book details"

        info_hash = details.get("info_hash")
        if not info_hash or info_hash == "Unknown":
            # Specific error constant used in routes.py
            from ..constants import ERROR_HASH_NOT_FOUND

            return None, ERROR_HASH_NOT_FOUND

        # Construct Magnet Link
        # urn:btih:<hash>&dn=<title>&tr=<tracker>
        magnet = f"magnet:?xt=urn:btih:{info_hash}"

        title = details.get("title")
        if title and title != "Unknown Title":
            from urllib.parse import quote

            magnet += f"&dn={quote(title)}"

        trackers = details.get("trackers", [])
        # Add trackers from details
        for tr in trackers:
            magnet += f"&tr={tr}"

        # Add default trackers if not present
        default_trackers = network.get_trackers()
        for tr in default_trackers:
            if tr not in trackers:
                magnet += f"&tr={tr}"

        return magnet, None

    except Exception as e:
        logger.error(f"Magnet: Error generating link for {url}: {e}")
        return None, f"Error generating magnet link: {e}"
