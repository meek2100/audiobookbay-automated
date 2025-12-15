# scripts/manage_headers.py
"""Universal utility to check or enforce file headers (banners).

Usage:
    # Check only (exit 1 if missing)
    python3 scripts/manage_headers.py file1.py file2.js

    # Check and Fix (exit 1 if modified)
    python3 scripts/manage_headers.py --fix file1.py file2.js
"""

import argparse
import os
import sys

# Configuration: Comment styles for various extensions
COMMENT_STYLES = {
    ".py": "# {}",
    ".yaml": "# {}",
    ".yml": "# {}",
    ".sh": "# {}",
    ".js": "// {}",
    ".css": "/* {} */",
    ".html": "",
    ".md": "",
}

# Safety Net: Files/Dirs to ignore even if passed by pre-commit
SKIP_FILES = {"package.json", "package-lock.json", ".DS_Store"}


def get_expected_header(filepath: str) -> str | None:
    """Generate the expected header string based on file extension."""
    _, ext = os.path.splitext(filepath)
    if ext not in COMMENT_STYLES:
        return None

    # Normalize to forward slashes for consistency across OS
    clean_path = filepath.replace("\\", "/")

    # Strip leading './' if present
    if clean_path.startswith("./"):
        clean_path = clean_path[2:]

    return COMMENT_STYLES[ext].format(clean_path) + "\n"


def process_file(filepath: str, fix_mode: bool) -> bool:
    """Process a single file.

    Args:
        filepath: Path to the file.
        fix_mode: If True, write changes. If False, just check.

    Returns:
        True if the file was modified (fix mode) or has missing header (check mode).
        False if compliant.
    """
    filename = os.path.basename(filepath)
    if filename in SKIP_FILES:
        return False

    expected_header = get_expected_header(filepath)
    if not expected_header:
        return False

    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
    except (UnicodeDecodeError, OSError):
        return False  # Skip binary or unreadable files

    # 1. Determine insertion point (handle Shebangs)
    insert_idx = 0
    if lines and lines[0].startswith("#!"):
        insert_idx = 1

    # 2. Check existing header
    # We look at the line where the header *should* be
    header_missing = True
    if len(lines) > insert_idx:
        current_line = lines[insert_idx]
        # Loose check: if the path is in the line, we assume it's correct enough
        # to avoid fighting with manual edits (spaces, formatting)
        if expected_header.strip() in current_line:
            header_missing = False

    if not header_missing:
        return False

    # 3. Action based on mode
    if not fix_mode:
        # Just report failure
        print(f"Missing header: {filepath}")
        return True
    else:
        # Apply fix
        lines.insert(insert_idx, expected_header)
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"Fixed header: {filepath}")
        return True


def main() -> None:
    """Execute the file header enforcement logic."""
    parser = argparse.ArgumentParser(description="Enforce file path headers.")
    parser.add_argument("--fix", action="store_true", help="Automatically add missing headers.")
    parser.add_argument("filenames", nargs="*", help="Files to check.")
    args = parser.parse_args()

    files_impacted = 0

    for filepath in args.filenames:
        if process_file(filepath, args.fix):
            files_impacted += 1

    if files_impacted > 0:
        if args.fix:
            print(f"\n{files_impacted} files were updated with headers. Please stage the changes.")
        else:
            print(f"\n{files_impacted} files are missing headers. Run with --fix to apply.")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
