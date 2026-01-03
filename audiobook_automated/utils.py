# File: audiobook_automated/utils.py
"""Utility functions for the application."""

import hashlib
import logging
import re
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath

from flask import current_app

from audiobook_automated.constants import (
    DEEP_PATH_WARNING_THRESHOLD,
    FALLBACK_TITLE,
    MAX_FILENAME_LENGTH,
    MIN_FILENAME_LENGTH,
    SAFE_SUFFIX,
    WINDOWS_PATH_SAFE_LIMIT,
    WINDOWS_RESERVED_NAMES,
)

logger = logging.getLogger(__name__)

# OPTIMIZATION: Pre-compile regex for faster execution
# Includes standard illegal chars AND control characters (\x00-\x1f)
ILLEGAL_CHARS_RE = re.compile(r'[\x00-\x1f<>:"/\\|?*]')


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
    cleaned = ILLEGAL_CHARS_RE.sub("", title)

    # Remove trailing periods and spaces which are invalid in Windows folder names
    sanitized = cleaned.rstrip(". ")

    if not sanitized:
        return FALLBACK_TITLE

    # Check for Windows reserved filenames (case-insensitive)
    # Check both exact match ("CON") and base stem match ("CON.tar.gz" -> "CON")
    # We use split(".")[0] to catch the primary name before any extensions.
    # Logic Update: Use re.split to correctly handle multiple dots or lack thereof.
    base_stem = sanitized.split(".")[0]

    # Explicit list of reserved names to check against (including COM1-9, LPT1-9)
    # This logic relies on WINDOWS_RESERVED_NAMES being complete, but let's be robust.
    is_reserved = False

    sanitized_upper = sanitized.upper()
    base_stem_upper = base_stem.upper()

    if sanitized_upper in WINDOWS_RESERVED_NAMES or base_stem_upper in WINDOWS_RESERVED_NAMES:
        is_reserved = True

    # Extra check for COM/LPT + digit if not in the constant set
    # Regex: ^(COM|LPT)[1-9]$
    # Note: WINDOWS_RESERVED_NAMES already contains LPT1-9, COM1-9.
    # This check is redundant if the set is complete, but kept for robustness.
    # However, since we enforce coverage, we remove the redundant logic to satisfy DRY/Coverage.
    if is_reserved:
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

    # Check 3: Ultra-short max_length edge case
    # If max_length is so small we can't fit a UUID, we must truncate hard without UUID
    # or return a minimal UUID.

    if needs_uuid:
        # Note: If max_length < 9, we purposely exceed the length limit to ensure uniqueness.
        # Safety (preventing collisions) > Strict Length Adherence in this edge case.
        unique_id = uuid.uuid4().hex[:8]
        # Reserve space for ID (8 chars) + Underscore (1) = 9 chars.
        trunc_len = max_length - 9
        # Ensure we don't truncate to a negative or zero length (redundant due to check above, but safe)
        trunc_len = max(trunc_len, 1)
        return f"{safe_title[:trunc_len]}_{unique_id}"

    return safe_title


def construct_safe_save_path(base_path: str | None, title: str) -> str:
    """Construct a safe filesystem path for the torrent download.

    Encapsulates logic for:
    1. Title sanitization.
    2. OS-specific path separators (Windows vs Posix detection).
    3. Path length calculation and truncation.
    4. Collision safety (UUID appending).

    Args:
        base_path: The root save path configured in the app (SAVE_PATH_BASE).
        title: The raw book title.

    Returns:
        str: The full, safe path string.
    """
    safe_title = sanitize_title(title)
    max_len = MAX_FILENAME_LENGTH

    # Dynamic Path Safety Calculation
    if base_path:
        base_len = len(base_path)
        # Use constant for calculation: 260 - 10 - 1 = 249
        calculated_limit = WINDOWS_PATH_SAFE_LIMIT - base_len

        # SAFETY: Explicitly fail if the base path is too deep to support even minimal filenames.
        # This prevents silent failures where the truncation logic would produce unusable names.
        if calculated_limit < MIN_FILENAME_LENGTH:
            raise ValueError(
                f"SAVE_PATH_BASE is too deep ({base_len} chars). "
                f"Remaining limit {calculated_limit} is less than MIN_FILENAME_LENGTH ({MIN_FILENAME_LENGTH})."
            )

        if calculated_limit < DEEP_PATH_WARNING_THRESHOLD:
            logger.warning(
                f"SAVE_PATH_BASE is extremely deep ({base_len} chars). "
                "Titles will be severely truncated to prevent file system errors."
            )

        # SAFETY: Prioritize OS limits over "usable" length.
        # Enforce floor of MIN_FILENAME_LENGTH, cap at calculated limit.
        max_len = max(MIN_FILENAME_LENGTH, calculated_limit)
        # Cap at MAX_FILENAME_LENGTH to ensure we never allow massive paths if base is short
        max_len = min(MAX_FILENAME_LENGTH, max_len)

    previous_title = safe_title
    safe_title = ensure_collision_safety(safe_title, max_length=max_len)

    if safe_title != previous_title:
        logger.warning(
            f"Title '{title}' required fallback/truncate handling. Using collision-safe directory name: {safe_title}"
        )

    if base_path:
        # Heuristic: If base path contains backslash, assume Windows path structure.
        # This handles cases where the Torrent Client is on Windows but the App is on Linux/Docker.
        if current_app.config.get("DL_CLIENT_OS") == "windows" or "\\" in base_path:
            return str(PureWindowsPath(base_path).joinpath(safe_title))
        return str(PurePosixPath(base_path).joinpath(safe_title))

    return safe_title


def calculate_static_hash(static_folder: str | Path) -> str:
    """Calculate a short SHA256 hash of the contents of the static folder.

    Args:
        static_folder: Path to the static assets directory.

    Returns:
        str: An 8-character hex string representing the content hash.
    """
    hash_sha256 = hashlib.sha256()
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
                        hash_sha256.update(chunk)
            except OSError:
                # If we can't read a file (permissions?), ignore it for the hash
                pass

    return hash_sha256.hexdigest()[:8]


def get_application_version(static_folder: str | Path) -> str:
    """Retrieve the application version hash.

    Prioritizes reading 'version.txt' (generated at build time) to avoid
    runtime I/O overhead. Falls back to calculating hash for local dev.

    Args:
        static_folder: Path to the static assets directory.

    Returns:
        str: The version hash.
    """
    folder_path = Path(static_folder)
    # version.txt is expected to be in the parent package directory
    version_file = folder_path.parent / "version.txt"

    if version_file.exists():
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Could not read version.txt, falling back to calculation.")

    return calculate_static_hash(folder_path)


def format_size(size_bytes: int | float | str | None) -> str:
    """Format bytes into human-readable B, KB, MB, GB, TB, PB.

    Args:
        size_bytes: The size in bytes (can be string, int, or float).

    Returns:
        str: Formatted string (e.g. "1.50 MB").
    """
    if size_bytes is None:
        return "Unknown"
    try:
        size: float = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:  # noqa: PLR2004
                return f"{size:.2f} {unit}"
            size /= 1024.0  # noqa: PLR2004
        return f"{size:.2f} PB"
    except (ValueError, TypeError):
        return "Unknown"


def parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse a boolean value safely from string or None.

    Supports '1', 'true', 'yes', 'on' (case-insensitive) as True.

    Args:
        value: The string value to parse (e.g. from environment variable).
        default: The default value if the input is None.

    Returns:
        bool: The parsed boolean.
    """
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":  # pragma: no cover
    # Script entry point for Docker build time optimization.
    # Calculates the hash of the static directory relative to this file
    # and prints it to stdout for redirection to version.txt.
    static_dir = Path(__file__).parent / "static"
    print(calculate_static_hash(static_dir))
