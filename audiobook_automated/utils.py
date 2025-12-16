"""Utility functions for the application."""

import hashlib
import re
import uuid
from pathlib import Path

from audiobook_automated.constants import FALLBACK_TITLE, SAFE_SUFFIX, WINDOWS_RESERVED_NAMES


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
        return f"{sanitized}{SAFE_SUFFIX}"

    return sanitized


def ensure_collision_safety(safe_title: str, max_length: int = 240) -> str:
    """Ensure a sanitized title is safe for filesystem creation by handling collisions and length limits.

    If the title matches the fallback, ends with the safe suffix (indicating a
    reserved name collision), or exceeds the max_length, a UUID is appended/truncated
    to ensure uniqueness and filesystem safety.

    Args:
        safe_title: The already sanitized title string.
        max_length: The maximum allowed length for the directory name (default 240).

    Returns:
        str: The collision-safe title, potentially truncated and with a UUID appended.
    """
    needs_uuid = False

    # Check 1: Reserved Name Collision or Fallback
    if safe_title == FALLBACK_TITLE or safe_title.endswith(SAFE_SUFFIX):
        needs_uuid = True

    # Check 2: Length Safety
    # If the title is too long, we force UUID logic to safely truncate
    if len(safe_title) > max_length:
        needs_uuid = True

    if needs_uuid:
        unique_id = uuid.uuid4().hex[:8]
        # Reserve space for ID (8 chars) + Underscore (1) = 9 chars.
        trunc_len = max_length - 9
        # Ensure we don't truncate to a negative or zero length
        trunc_len = max(trunc_len, 1)
        return f"{safe_title[:trunc_len]}_{unique_id}"

    return safe_title


def calculate_static_hash(static_folder: str | Path) -> str:
    """Calculate a short MD5 hash of the contents of the static folder.

    This is used for cache-busting: if any static file changes, this hash
    will change, forcing browsers to download the new version.

    Args:
        static_folder: Path to the static assets directory.

    Returns:
        str: An 8-character hex string representing the content hash.
    """
    hash_md5 = hashlib.md5()  # nosec B324  # noqa: S324
    folder_path = Path(static_folder)

    if not folder_path.exists():
        return "v1"

    # Walk through the static folder to hash all file contents
    # Use sorted() to ensure consistent hashing order across systems
    for path in sorted(folder_path.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            try:
                with path.open("rb") as f:
                    # Read in chunks to handle large files efficiently
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
            except OSError:
                # If we can't read a file (permissions?), ignore it for the hash
                pass

    # Return first 8 chars (sufficient for uniqueness)
    return hash_md5.hexdigest()[:8]


if __name__ == "__main__":  # pragma: no cover
    # Script entry point for Docker build time optimization.
    # Calculates the hash of the static directory relative to this file
    # and prints it to stdout for redirection to version.txt.
    static_dir = Path(__file__).parent / "static"
    print(calculate_static_hash(static_dir))
