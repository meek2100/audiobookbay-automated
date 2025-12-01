import re


def sanitize_title(title: str | None) -> str:
    """
    Sanitizes a string to be safe for use as a directory name.
    Removes characters like < > : " / \ | ? *
    Also removes trailing periods and spaces (Windows compatibility).

    Args:
        title: The string to sanitize, potentially None.

    Returns:
        A sanitized string safe for use as a directory name.
    """
    if not title:
        return ""
    # Remove illegal characters
    cleaned = re.sub(r'[<>:"/\\|?*]', "", title)
    # Remove trailing periods and spaces which are invalid in Windows folder names
    return cleaned.strip(". ")
