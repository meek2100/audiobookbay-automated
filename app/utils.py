import re


def sanitize_title(title: str | None) -> str:
    r"""
    Sanitizes a string to be safe for use as a directory name.
    Removes characters like < > : " / \ | ? *
    Also removes trailing periods and spaces (Windows compatibility).
    Returns "Unknown_Title" if the resulting string is empty to prevent
    file operations in the root directory.

    Args:
        title: The string to sanitize, potentially None.

    Returns:
        A sanitized string safe for use as a directory name, or "Unknown_Title".
    """
    if not title:
        return "Unknown_Title"

    # Remove illegal characters
    cleaned = re.sub(r'[<>:"/\\|?*]', "", title)

    # Remove trailing periods and spaces which are invalid in Windows folder names
    sanitized = cleaned.strip(". ")

    # Return fallback if sanitization stripped everything
    return sanitized if sanitized else "Unknown_Title"
