import re

from bs4 import Tag

# --- Regex Patterns ---
# Why: AudioBookBay formats the info table unpredictably.
# These regexes allow us to match table cells even if casing or whitespace changes slightly.
RE_INFO_HASH = re.compile(r"Info Hash", re.IGNORECASE)
RE_HASH_STRING = re.compile(r"\b([a-fA-F0-9]{40})\b")
RE_TRACKERS = re.compile(r".*(?:udp|http)://.*", re.IGNORECASE)


def get_text_after_label(container: Tag, label_text: str) -> str:
    """
    Robustly finds values based on a label within a BS4 container.

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
            return val

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
