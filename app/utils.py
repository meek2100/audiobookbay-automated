import re

def sanitize_title(title):
    """
    Sanitizes a string to be safe for use as a directory name.
    Removes characters like < > : " / \ | ? *
    Also removes trailing periods and spaces (Windows compatibility).
    """
    if not title:
        return ""
    # Remove illegal characters
    cleaned = re.sub(r'[<>:"/\\|?*]', "", title)
    # Remove trailing periods and spaces which are invalid in Windows folder names
    return cleaned.strip(". ")