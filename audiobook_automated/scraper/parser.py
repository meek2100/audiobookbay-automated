# audiobook_automated/scraper/parser.py
"""Parser module for BeautifulSoup HTML processing.

This module contains regex patterns and helper functions to extract
structured data from the raw HTML of AudiobookBay pages.
It encapsulates parsing strategies to keep core.py focused on networking and flow control.
"""

import re
from dataclasses import dataclass, field, fields
from typing import TypedDict
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from audiobook_automated.constants import DEFAULT_COVER_FILENAME

# Constants
MIN_TABLE_CELLS = 2

# --- Regex Patterns ---
# Why: AudioBookBay formats the info table unpredictably.
# These regexes allow us to match table cells even if casing or whitespace changes slightly.
RE_INFO_HASH = re.compile(r"Info Hash", re.IGNORECASE)
# FUTURE PROOF: Updated to support SHA-1 (40 hex) and BitTorrent v2 SHA-256 (64 hex)
RE_HASH_STRING = re.compile(r"\b([a-fA-F0-9]{40}|[a-fA-F0-9]{64})\b")

# OPTIMIZATION: Module-level compilation for frequently used patterns in loops
RE_LANGUAGE = re.compile(r"Language:\s*(\S+)", re.IGNORECASE)
# Robustness: Allow for end of string or 'Language:' as terminator for Category capture.
# This prevents failure if the layout changes and 'Language:' is missing.
RE_CATEGORY = re.compile(r"Category:\s*(.+?)(?:\s+Language:|\s*$)", re.IGNORECASE)

# Pre-compiled label patterns for parsing content
# Robustness: Use IGNORECASE and allow optional whitespace for reliability
RE_LABEL_POSTED = re.compile(r"Posted:", re.IGNORECASE)
RE_LABEL_FORMAT = re.compile(r"Format:", re.IGNORECASE)
RE_LABEL_BITRATE = re.compile(r"Bitrate:", re.IGNORECASE)
RE_LABEL_SIZE = re.compile(r"File\s*Size:", re.IGNORECASE)


class BookSummary(TypedDict):
    """TypedDict representing the structure of a search result (summary)."""

    title: str
    link: str
    cover: str | None
    language: str
    category: list[str]
    post_date: str
    format: str
    bitrate: str
    file_size: str


class BookDetails(BookSummary):
    """TypedDict representing the full details of a book.

    Inherits from BookSummary and adds fields available only on the details page.
    """

    description: str
    trackers: list[str]
    info_hash: str
    author: str
    narrator: str


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
        # COMPLIANCE: Python 3.13+ / Pylance strict type check
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
        # Explicit cast to str for Pylance safety
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


def _normalize_metadata(meta: BookMetadata) -> None:
    """Normalize metadata fields in place, handling unknown values.

    Iterates through all fields in the BookMetadata dataclass and ensures
    '?' or empty strings are converted to "Unknown".
    """
    for f in fields(meta):
        value = getattr(meta, f.name)

        # 1. Normalize Categories (List)
        if f.name == "category":
            if not value:
                setattr(meta, f.name, ["Unknown"])
            else:
                # Iterate and normalize individual items in the list
                normalized_list = []
                for item in value:
                    # Check for '?', empty strings, or strings that are just whitespace/punctuation
                    if not item or item.strip() in ["?", ""]:
                        normalized_list.append("Unknown")
                    else:
                        normalized_list.append(item)
                setattr(meta, f.name, normalized_list)
            continue

        # 2. Normalize Strings (File Size, Bitrate, etc.)
        # TYPE SAFETY: Explicitly guard against 'category' list leaking here
        if isinstance(value, str):
            # Strip whitespace and check against invalid values
            clean_val = value.strip()
            if not clean_val or clean_val == "?" or clean_val.startswith("? "):
                setattr(meta, f.name, "Unknown")


def _parse_body_content(content_div: Tag, meta: BookMetadata) -> None:
    """Extract metadata (Posted, Format, Bitrate, Size) from the body paragraphs.

    Args:
        content_div: The div containing the content paragraphs.
        meta: The metadata object to update in place.
    """
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


def parse_post_content(
    content_div: Tag | None,
    post_info: Tag | None,
    author_tag: Tag | None = None,
    narrator_tag: Tag | None = None,
) -> BookMetadata:
    """Parse the post content and info sections to extract normalized metadata.

    Refactored to reduce complexity by delegating normalization and body parsing.

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
        _parse_body_content(content_div, meta)

    # Parse People (Author/Narrator)
    if author_tag:
        meta.author = author_tag.get_text(strip=True)
    if narrator_tag:
        meta.narrator = narrator_tag.get_text(strip=True)

    # Apply Normalization
    _normalize_metadata(meta)

    return meta


def _sanitize_description(desc_tag: Tag | None) -> str:
    """Extract and sanitize the description from the description tag.

    Args:
        desc_tag: The BeautifulSoup Tag containing the description.

    Returns:
        str: The sanitized HTML description string.
    """
    if not desc_tag:
        return "No description available."

    # Strict HTML Sanitization
    allowed_tags = ["p", "br", "b", "i", "em", "strong", "ul", "li"]
    # SAFETY: Iterate over a list copy to safely modify the tree during iteration
    for tag in list(desc_tag.find_all(True)):
        if tag.name not in allowed_tags:
            # IMPROVEMENT: Insert a space before unwrapping to prevent block-level elements
            # from merging their text contents (e.g. "<div>A</div><div>B</div>" -> "AB").
            tag.insert_after(" ")
            tag.unwrap()
        else:
            tag.attrs = {}  # Strip attributes like onclick, style, etc.
    return str(desc_tag.decode_contents())


def _extract_table_data(info_table: Tag | None, file_size_fallback: str) -> tuple[list[str], str, str]:
    """Extract trackers, file size, and info hash from the torrent info table.

    Args:
        info_table: The table Tag.
        file_size_fallback: The current file size to fallback on if not found in table.

    Returns:
        tuple[list[str], str, str]: A tuple of (trackers, updated_file_size, info_hash).
    """
    trackers = []
    file_size = file_size_fallback
    info_hash = "Unknown"

    if info_table:
        for row in info_table.find_all("tr"):
            cells = row.find_all("td")
            # Replaced magic value '2' with constant
            if len(cells) >= MIN_TABLE_CELLS:
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
    return trackers, file_size, info_hash


def _find_info_hash_fallback(soup: BeautifulSoup, current_hash: str) -> str:
    """Find the info hash using fallback strategies if not found in the table.

    Args:
        soup: The main page soup.
        current_hash: The currently extracted hash (usually "Unknown").

    Returns:
        str: The discovered hash or "Unknown".
    """
    if current_hash != "Unknown":
        return current_hash

    # Fallback 1: Footer Hash
    # Robustness: Search for text content recursively to handle nested tags (e.g., <b>Info Hash:</b>)
    info_hash_row = soup.find(lambda tag: tag.name == "td" and bool(RE_INFO_HASH.search(tag.get_text())))
    if info_hash_row:
        sibling = info_hash_row.find_next_sibling("td")
        if sibling:
            return str(sibling.text.strip())

    # Fallback 2: Regex on full text
    # Note: soup.text approximates the raw text content.
    # RE_HASH_STRING usually finds the hex string in the text nodes.
    hash_match = RE_HASH_STRING.search(str(soup))
    if hash_match:
        return hash_match.group(1)

    return "Unknown"


def parse_book_details(soup: BeautifulSoup, url: str) -> BookDetails:
    """Extract full book details from the BeautifulSoup object of a details page.

    Centralizes parsing logic for the details view, including sanitization
    and hash extraction.

    Args:
        soup: The parsed HTML soup object.
        url: The source URL (used for cover normalization and link attribution).

    Returns:
        BookDetails: A typed dictionary containing the complete scraped data.
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

    # Helper 1: Sanitize Description
    description = _sanitize_description(soup.select_one("div.desc"))

    # Helper 2: Extract Table Data
    trackers, file_size, info_hash = _extract_table_data(
        soup.select_one("table.torrent_info"),
        meta.file_size,
    )

    # Helper 3: Fallback Hash Extraction
    info_hash = _find_info_hash_fallback(soup, info_hash)

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
