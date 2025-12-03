import hashlib
import os
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


def calculate_static_hash(static_folder: str) -> str:
    """
    Calculates a short MD5 hash of the contents of the static folder.
    This is used for cache-busting: if any static file changes, this hash
    will change, forcing browsers to download the new version.

    Args:
        static_folder: Path to the static assets directory.

    Returns:
        str: An 8-character hex string representing the content hash.
    """
    hash_md5 = hashlib.md5()

    if not os.path.exists(static_folder):
        return "v1"

    # Walk through the static folder to hash all file contents
    for root, dirs, files in os.walk(static_folder):
        # Sort to ensure consistent hashing order across systems
        dirs.sort()
        files.sort()
        for filename in files:
            # Skip hidden files
            if filename.startswith("."):
                continue

            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "rb") as f:
                    # Read in chunks to handle large files efficiently
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
            except (IOError, OSError):
                # If we can't read a file (permissions?), ignore it for the hash
                pass

    # Return first 8 chars (sufficient for uniqueness)
    return hash_md5.hexdigest()[:8]
