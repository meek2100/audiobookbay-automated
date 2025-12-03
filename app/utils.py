import re


def sanitize_title(title: str | None) -> str:
    r"""
    Sanitizes a string to be safe for use as a directory name.
    Removes characters like < > : " / \ | ? *
    Also removes trailing periods and spaces (Windows compatibility).
    Returns "Unknown_Title" if the resulting string is empty to prevent
    file operations in the root directory.

    Also checks for Windows reserved filenames (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    to ensure compatibility with SMB shares/Windows mounts.

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

    if not sanitized:
        return "Unknown_Title"

    # Check for Windows reserved filenames (case-insensitive)
    # CON, PRN, AUX, NUL, COM1-9, LPT1-9
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    if sanitized.upper() in reserved_names:
        return f"{sanitized}_Safe"

    return sanitized
