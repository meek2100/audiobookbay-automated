"""Scraper package for AudiobookBay content."""

from app.constants import DEFAULT_TRACKERS, USER_AGENTS

from .core import extract_magnet_link, fetch_and_parse_page, get_book_details, search_audiobookbay
from .network import (
    ABB_FALLBACK_HOSTNAMES,
    PAGE_LIMIT,
    check_mirror,
    find_best_mirror,
    get_random_user_agent,
    get_session,
    load_trackers,
    mirror_cache,
    search_cache,
)

# FIX: Import the public name 'get_text_after_label' and 'BookDict' directly
from .parser import BookDict, get_text_after_label

# Expose public API
__all__ = [
    "extract_magnet_link",
    "get_book_details",
    "search_audiobookbay",
    "fetch_and_parse_page",
    "ABB_FALLBACK_HOSTNAMES",
    "DEFAULT_TRACKERS",
    "PAGE_LIMIT",
    "USER_AGENTS",
    "check_mirror",
    "find_best_mirror",
    "get_random_user_agent",
    "get_session",
    "load_trackers",
    "mirror_cache",
    "search_cache",
    "get_text_after_label",
    "BookDict",
]
