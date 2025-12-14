"""Parser module for BeautifulSoup HTML processing.

This module contains regex patterns and helper functions to extract
structured data from the raw HTML of AudiobookBay pages.
It encapsulates parsing strategies to keep core.py focused on networking and flow control.
"""

import re
from dataclasses import dataclass, field, fields
from typing import NotRequired, Optional, TypedDict
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from audiobook_automated.constants import DEFAULT_COVER_FILENAME

# --- Regex Patterns ---
# Why: AudioBookBay formats the info table unpredictably.
# These regexes allow us to match table cells even if casing or whitespace changes slightly.
RE_INFO_HASH = re.compile(r"Info Hash", re.IGNORECASE)
# FUTURE PROOF: Updated to support SHA-1 (40 hex) and BitTorrent v2 SHA-256 (64 hex)
RE_HASH_STRING = re.compile(r"\b([a-fA-F0-9]{40}|[a-fA-F0-9]{64})\b")

# OPTIMIZATION: Module-level compilation for frequently used patterns in loops
RE_LANGUAGE = re.compile(r"Language:\s*(\S+)", re.IGNORECASE)
RE_CATEGORY = re.compile(r"Category:\s*(.+?)(?:\s+Language:|$)")

# Pre-compiled label patterns for parsing content
# Robustness: Use IGNORECASE and allow optional whitespace for reliability
RE_LABEL_POSTED = re.compile(r"Posted:", re.IGNORECASE)
RE_LABEL_FORMAT = re.compile(r"Format:", re.IGNORECASE)
RE_LABEL_BITRATE = re.compile(r"Bitrate:", re.IGNORECASE)
RE_LABEL_SIZE = re.compile(r"File\s*Size:", re.IGNORECASE)


class BookDict(TypedDict):
    """TypedDict representing the structure of a parsed book dictionary."""

    title: str
    link: str
    cover: str | None
    description: NotRequired[str]
    trackers: NotRequired[list[str]]
    info_hash: NotRequired[str]
    language: str
    category: list[str]  # Changed to list to support multiple tags
    post_date: str
    format: str
    bitrate: str
    file_size: str
    author: NotRequired[str]
    narrator: NotRequired[str]


@dataclass
class BookMetadata:
    """Data class representing standard audiobook metadata extracted from the page."""

    language: str = "Unknown"
    # Use default_factory for mutable defaults (list)
    category: list[str] = field(default_factory=lambda: ["Unknown"])
    post_date: str = "Unknown"
    format: str = "Unknown"
    bitrate: str = "Unknown"
    file_size: str = "Unknown"
    author: str = "Unknown"
    narrator: str = "Unknown"


def get_text_after_label(container: Tag, label_pattern: re.Pattern[str], is_file_size: bool = False) -> str:
    """Robustly find values based on a label within a BS4 container using a compiled regex.

    Strategy:
    1. Finds the text node containing the pattern.
    2. Strategy 1: Checks the next sibling element (e.g., <span>Value</span>).
    3. Strategy 2: If no sibling, attempts to parse the value from the text node itself.

    Args:
        container: The BeautifulSoup Tag to search within.
        label_pattern: The compiled regex pattern to search for.
        is_file_size: Flag to enable specific logic for file size units.

    Returns:
        str: The extracted value, or "Unknown" if not found.
    """
    try:
        # Find the text string (e.g., "Format:")
        label_node = container.find(string=label_pattern)
        if not label_node:
            return "Unknown"

        # Strategy 1: The value is in the next sibling element (e.g., <span>MP3</span>)
        next_elem = label_node.find_next_sibling()
        # COMPLIANCE: Python 3.13 / Pylance strict type check
        if next_elem and isinstance(next_elem, Tag) and next_elem.name == "span":
            val = next_elem.get_text(strip=True)
            # Special handling for File Size which might have unit in next text node
            if is_file_size:
                unit_node = next_elem.next_sibling
                if unit_node and isinstance(unit_node, str):
                    val += f" {unit_node.strip()}"
            return str(val)

        # Strategy 2: The value is in the same text node (e.g., "Posted: 30 Nov 2025")
        # Split by the label and take the rest
        # Explicit cast to str for Pylance/Python 3.13 safety
        label_str = str(label_node)
        if ":" in label_str:
            parts = label_str.split(":", 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()

        return "Unknown"
    except Exception:
        return "Unknown"


def normalize_cover_url(base_url: str, relative_url: str) -> str | None:
    """Normalize a cover image URL and handle default placeholders.

    Args:
        base_url: The base URL of the page (for joining relative paths).
        relative_url: The raw 'src' attribute from the image tag.

    Returns:
        str | None: The absolute URL if valid and not the default placeholder, else None.
    """
    if not relative_url:
        return None

    extracted_cover = urljoin(base_url, relative_url)
    # If remote is the default placeholder, return None so UI uses the local versioned asset
    if extracted_cover.endswith(DEFAULT_COVER_FILENAME):
        return None

    return extracted_cover


def parse_post_content(
    content_div: Optional[Tag],
    post_info: Optional[Tag],
    author_tag: Optional[Tag] = None,
    narrator_tag: Optional[Tag] = None,
) -> BookMetadata:
    """Parse the post content and info sections to extract normalized metadata.

    Handles '?' to 'Unknown' conversion centrally.

    Args:
        content_div: The div containing the main post content (p tags).
        post_info: The div containing the header info (Category, Language).
        author_tag: Optional BeautifulSoup Tag containing author info.
        narrator_tag: Optional BeautifulSoup Tag containing narrator info.

    Returns:
        BookMetadata: A dataclass containing the extracted and normalized fields.
    """
    meta = BookMetadata()

    # Parse Info Header (Language, Category)
    if post_info:
        info_text = post_info.get_text(" ", strip=True)
        lang_match = RE_LANGUAGE.search(info_text)
        if lang_match:
            meta.language = lang_match.group(1)

        cat_match = RE_CATEGORY.search(info_text)
        if cat_match:
            raw_cat = cat_match.group(1).strip()
            # Split comma-separated categories into a list
            if raw_cat:
                meta.category = [c.strip() for c in raw_cat.split(",") if c.strip()]

    # Parse Body Paragraphs
    if content_div:
        for p in content_div.find_all("p"):
            p_text = p.get_text()
            if RE_LABEL_POSTED.search(p_text):
                meta.post_date = get_text_after_label(p, RE_LABEL_POSTED)
            if RE_LABEL_FORMAT.search(p_text):
                meta.format = get_text_after_label(p, RE_LABEL_FORMAT)
            if RE_LABEL_BITRATE.search(p_text):
                meta.bitrate = get_text_after_label(p, RE_LABEL_BITRATE)
            if RE_LABEL_SIZE.search(p_text):
                meta.file_size = get_text_after_label(p, RE_LABEL_SIZE, is_file_size=True)

    # Parse People (Author/Narrator)
    if author_tag:
        meta.author = author_tag.get_text(strip=True)
    if narrator_tag:
        meta.narrator = narrator_tag.get_text(strip=True)

    # Normalization Rule: Convert "?" or empty strings to "Unknown"
    # We iterate over the dataclass fields to ensure consistent normalization
    for f in fields(meta):
        value = getattr(meta, f.name)

        # Special handling for category list (prevent ["Unknown"] overwritten by empty check)
        if f.name == "category":
            if not value:
                setattr(meta, f.name, ["Unknown"])
            continue

        # Standard handling for strings
        if isinstance(value, str):
            if value == "?" or not value or not value.strip():
                setattr(meta, f.name, "Unknown")

    return meta


def parse_book_details(soup: BeautifulSoup, url: str) -> BookDict:
    """Extract full book details from the BeautifulSoup object of a details page.

    Centralizes parsing logic for the details view, including sanitization
    and hash extraction.

    Args:
        soup: The parsed HTML soup object.
        url: The source URL (used for cover normalization and link attribution).

    Returns:
        BookDict: A dictionary containing the scraped data.
    """
    title = "Unknown Title"
    title_tag = soup.select_one(".postTitle h1")
    if title_tag:
        title = title_tag.get_text(strip=True)

    cover = None
    cover_tag = soup.select_one('.postContent img[itemprop="image"]')
    if cover_tag and cover_tag.has_attr("src"):
        cover = normalize_cover_url(url, str(cover_tag["src"]))

    post_info = soup.select_one(".postInfo")
    content_div = soup.select_one(".postContent")
    author_tag = soup.select_one('span.author[itemprop="author"]')
    narrator_tag = soup.select_one('span.narrator[itemprop="author"]')

    meta = parse_post_content(content_div, post_info, author_tag, narrator_tag)

    # --- Description Extraction & Sanitization ---
    description = "No description available."
    desc_tag = soup.select_one("div.desc")
    if desc_tag:
        # Strict HTML Sanitization
        allowed_tags = ["p", "br", "b", "i", "em", "strong", "ul", "li"]
        # SAFETY: Iterate over a list copy to safely modify the tree during iteration
        for tag in list(desc_tag.find_all(True)):
            if tag.name not in allowed_tags:
                tag.unwrap()
            else:
                tag.attrs = {}  # Strip attributes like onclick, style, etc.
        description = desc_tag.decode_contents()

    # --- Tracker & Hash Extraction ---
    trackers = []
    file_size = meta.file_size
    info_hash = "Unknown"

    info_table = soup.select_one("table.torrent_info")
    if info_table:
        for row in info_table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)

                if value == "?" or not value:
                    value = "Unknown"

                if "Tracker:" in label or "Announce URL:" in label:
                    trackers.append(value)
                elif "File Size:" in label and file_size == "Unknown":
                    file_size = value
                elif "Info Hash:" in label:
                    info_hash = value

    # Fallback 1: Footer Hash
    if info_hash == "Unknown":
        # Robustness: Search for text content recursively to handle nested tags (e.g., <b>Info Hash:</b>)
        info_hash_row = soup.find(lambda tag: tag.name == "td" and bool(RE_INFO_HASH.search(tag.get_text())))
        if info_hash_row:
            sibling = info_hash_row.find_next_sibling("td")
            if sibling:
                info_hash = sibling.text.strip()

    # Fallback 2: Regex on full text
    if info_hash == "Unknown":
        # Note: We don't have response.text here, but soup.text approximates it.
        # Ideally, regex works better on raw HTML.
        # However, passed `soup` implies we work on DOM.
        # If regex is critical, we might miss it if split across tags.
        # But RE_HASH_STRING usually finds the hex string in the text nodes.
        hash_match = RE_HASH_STRING.search(str(soup))
        if hash_match:
            info_hash = hash_match.group(1)

    return {
        "title": title,
        "cover": cover,
        "description": description,
        "trackers": trackers,
        "file_size": file_size,
        "info_hash": info_hash,
        "link": url,
        "language": meta.language,
        "category": meta.category,
        "post_date": meta.post_date,
        "format": meta.format,
        "bitrate": meta.bitrate,
        "author": meta.author,
        "narrator": meta.narrator,
    }
