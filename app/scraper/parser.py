"""Parser module for BeautifulSoup HTML processing.

This module contains regex patterns and helper functions to extract
structured data from the raw HTML of AudiobookBay pages.
It encapsulates parsing strategies to keep core.py focused on networking and flow control.
"""

import re
from dataclasses import dataclass, fields
from typing import NotRequired, Optional, TypedDict

from bs4 import Tag

# --- Regex Patterns ---
# Why: AudioBookBay formats the info table unpredictably.
# These regexes allow us to match table cells even if casing or whitespace changes slightly.
RE_INFO_HASH = re.compile(r"Info Hash", re.IGNORECASE)
RE_HASH_STRING = re.compile(r"\b([a-fA-F0-9]{40})\b")

# OPTIMIZATION: Module-level compilation for frequently used patterns in loops
RE_LANGUAGE = re.compile(r"Language:\s*(\S+)")
RE_CATEGORY = re.compile(r"Category:\s*(.+?)(?:\s+Language:|$)")


class BookDict(TypedDict):
    """TypedDict representing the structure of a parsed book dictionary."""

    title: str
    link: str
    cover: str | None
    description: NotRequired[str]
    trackers: NotRequired[list[str]]
    info_hash: NotRequired[str]
    language: str
    category: str
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
    category: str = "Unknown"
    post_date: str = "Unknown"
    format: str = "Unknown"
    bitrate: str = "Unknown"
    file_size: str = "Unknown"


def get_text_after_label(container: Tag, label_text: str) -> str:
    """Robustly find values based on a label within a BS4 container.

    Strategy:
    1. Finds the text node containing 'label_text'.
    2. Checks the next sibling element (e.g., <span>Value</span>).
    3. If no sibling, attempts to parse the value from the text node itself.

    Args:
        container: The BeautifulSoup Tag to search within.
        label_text: The label string to search for (e.g. "Format:").

    Returns:
        str: The extracted value, or "Unknown" if not found.
    """
    try:
        # Find the text string (e.g., "Format:")
        label_node = container.find(string=re.compile(label_text))
        if not label_node:
            return "Unknown"

        # Strategy 1: The value is in the next sibling element (e.g., <span>MP3</span>)
        next_elem = label_node.find_next_sibling()
        # COMPLIANCE: Python 3.13 / Pylance strict type check
        if next_elem and isinstance(next_elem, Tag) and next_elem.name == "span":
            val = next_elem.get_text(strip=True)
            # Special handling for File Size which might have unit in next text node
            if "File Size" in label_text:
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


def parse_post_content(content_div: Optional[Tag], post_info: Optional[Tag]) -> BookMetadata:
    """Parse the post content and info sections to extract normalized metadata.

    Handles '?' to 'Unknown' conversion centrally.

    Args:
        content_div: The div containing the main post content (p tags).
        post_info: The div containing the header info (Category, Language).

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
            meta.category = cat_match.group(1).strip()

    # Parse Body Paragraphs
    if content_div:
        for p in content_div.find_all("p"):
            p_text = p.get_text()
            if "Posted:" in p_text:
                meta.post_date = get_text_after_label(p, "Posted:")
            if "Format:" in p_text:
                meta.format = get_text_after_label(p, "Format:")
            if "Bitrate:" in p_text:
                meta.bitrate = get_text_after_label(p, "Bitrate:")
            if "File Size:" in p_text:
                meta.file_size = get_text_after_label(p, "File Size:")

    # Normalization Rule: Convert "?" or empty strings to "Unknown"
    # We iterate over the dataclass fields to ensure consistent normalization
    for field in fields(meta):
        value = getattr(meta, field.name)
        if value == "?" or not value or not value.strip():
            setattr(meta, field.name, "Unknown")

    return meta
