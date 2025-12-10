"""Utility functions for the application."""

import hashlib
import os
import re

from app.constants import FALLBACK_TITLE, WINDOWS_RESERVED_NAMES


def sanitize_title(title: str | None) -> str:
    r"""Sanitize a string to be safe for use as a directory name.

    Removes characters like < > : " / \ | ? *
    Also removes trailing periods and spaces (Windows compatibility).
    Returns FALLBACK_TITLE if the resulting string is empty to prevent
    file operations in the root directory.

    Also checks for Windows reserved filenames (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    to ensure compatibility with SMB shares/Windows mounts.
    Checks both the full name and the root name (e.g. "CON.txt" is also invalid).

    Args:
        title: The string to sanitize, potentially None.

    Returns:
        A sanitized string safe for use as a directory name, or FALLBACK_TITLE.
    """
    if not title:
        return FALLBACK_TITLE

    # Remove illegal characters
    cleaned = re.sub(r'[<>:"/\\|?*]', "", title)

    # Remove trailing periods and spaces which are invalid in Windows folder names
    sanitized = cleaned.strip(". ")

    if not sanitized:
        return FALLBACK_TITLE

    # Check for Windows reserved filenames (case-insensitive)
    # Check both exact match ("CON") and base stem match ("CON.tar.gz" -> "CON")
    # We use split(".")[0] to catch the primary name before any extensions.
    base_stem = sanitized.split(".")[0]

    if sanitized.upper() in WINDOWS_RESERVED_NAMES or base_stem.upper() in WINDOWS_RESERVED_NAMES:
        return f"{sanitized}_Safe"

    return sanitized


def calculate_static_hash(static_folder: str) -> str:
    """Calculate a short MD5 hash of the contents of the static folder.

    This is used for cache-busting: if any static file changes, this hash
    will change, forcing browsers to download the new version.

    Args:
        static_folder: Path to the static assets directory.

    Returns:
        str: An 8-character hex string representing the content hash.
    """
    hash_md5 = hashlib.md5()  # nosec B324

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


if __name__ == "__main__":  # pragma: no cover
    # Script entry point for build-time hash generation.
    # This allows us to calculate the hash once during Docker build
    # rather than every time the application starts up.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, "static")
    output_path = os.path.join(base_dir, "version.txt")

    print(f"Generating static asset hash for: {static_dir}")
    version_hash = calculate_static_hash(static_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(version_hash)

    print(f"Version hash '{version_hash}' written to: {output_path}")
