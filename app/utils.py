import re

def sanitize_title(title):
    """
    Sanitizes a string to be safe for use as a directory name.
    Removes characters like < > : " / \ | ? *
    """
    if not title:
        return ""
    return re.sub(r'[<>:"/\\|?*]', "", title).strip()