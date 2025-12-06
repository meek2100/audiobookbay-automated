import os
import tempfile
from typing import Any
from unittest.mock import patch

from app.constants import FALLBACK_TITLE
from app.utils import calculate_static_hash, sanitize_title

# --- Sanitize Title Tests ---


def test_sanitize_simple_title() -> None:
    assert sanitize_title("Harry Potter") == "Harry Potter"


def test_sanitize_special_chars() -> None:
    # Colons and slashes should be removed
    assert sanitize_title("Book: The Movie / Part 1") == "Book The Movie  Part 1"


def test_sanitize_windows_reserved() -> None:
    # Trailing periods and spaces are bad in Windows
    assert sanitize_title("The End. ") == "The End"


def test_sanitize_empty() -> None:
    """Test that explicit empty/None inputs fallback to FALLBACK_TITLE."""
    assert sanitize_title("") == FALLBACK_TITLE
    assert sanitize_title(None) == FALLBACK_TITLE


def test_sanitize_strips_to_empty() -> None:
    """Test that a title composed only of illegal chars falls back safely."""
    # A title like "..." cleans to "" then strips to "", so we need a fallback.
    assert sanitize_title("...") == FALLBACK_TITLE
    assert sanitize_title("???") == FALLBACK_TITLE


def test_sanitize_reserved_filenames() -> None:
    """Test that Windows reserved filenames are renamed safely."""
    # Exact match
    assert sanitize_title("CON") == "CON_Safe"
    assert sanitize_title("nul") == "nul_Safe"
    assert sanitize_title("LPT1") == "LPT1_Safe"
    # Partial match should remain untouched
    assert sanitize_title("CONFERENCE") == "CONFERENCE"
    assert sanitize_title("NULLIFY") == "NULLIFY"


def test_sanitize_reserved_filenames_with_extensions() -> None:
    """Test that reserved filenames with extensions are also caught (New Requirement)."""
    assert sanitize_title("CON.txt") == "CON.txt_Safe"
    assert sanitize_title("lpt1.mp3") == "lpt1.mp3_Safe"
    assert sanitize_title("AUX.json") == "AUX.json_Safe"


# --- Calculate Static Hash Tests ---


def test_calculate_static_hash_valid() -> None:
    """Test hashing a real temporary directory with files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a dummy file
        file_path = os.path.join(tmp_dir, "style.css")
        with open(file_path, "w") as f:
            f.write("body { color: red; }")

        # Create a subdirectory with a file
        sub_dir = os.path.join(tmp_dir, "js")
        os.mkdir(sub_dir)
        with open(os.path.join(sub_dir, "app.js"), "w") as f:
            f.write("console.log('hello');")

        # Calculate hash
        hash_val = calculate_static_hash(tmp_dir)

        # Assert it returns a string of expected length (8 chars)
        assert isinstance(hash_val, str)
        assert len(hash_val) == 8

        # Verify determinism: Same content should yield same hash
        assert calculate_static_hash(tmp_dir) == hash_val

        # Modify file and verify hash changes
        with open(file_path, "w") as f:
            f.write("body { color: blue; }")

        new_hash = calculate_static_hash(tmp_dir)
        assert new_hash != hash_val


def test_calculate_static_hash_ignore_hidden() -> None:
    """Test that hidden files (starting with .) are skipped.

    This covers the 'if filename.startswith("."): continue' branch.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Create a visible file
        visible_path = os.path.join(tmp_dir, "visible.txt")
        with open(visible_path, "w") as f:
            f.write("content")

        # 2. Get baseline hash
        hash_base = calculate_static_hash(tmp_dir)

        # 3. Add a hidden file
        hidden_path = os.path.join(tmp_dir, ".DS_Store")
        with open(hidden_path, "w") as f:
            f.write("junk_data")

        # 4. Get new hash
        hash_new = calculate_static_hash(tmp_dir)

        # 5. Assert equality (Hidden file should NOT change the hash)
        assert hash_base == hash_new


def test_calculate_static_hash_missing_dir() -> None:
    """Test that a missing directory returns the default fallback."""
    assert calculate_static_hash("/path/that/does/not/exist") == "v1"


def test_calculate_static_hash_empty_dir() -> None:
    """Test hashing an empty directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Should return a consistent hash for empty dir
        hash_val = calculate_static_hash(tmp_dir)
        assert len(hash_val) == 8


def test_calculate_static_hash_permission_error() -> None:
    """Test that unreadable files are skipped without crashing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        file_path = os.path.join(tmp_dir, "locked.txt")
        with open(file_path, "w") as f:
            f.write("secret")

        # Mock open() to raise PermissionError specifically for this file
        # We use a side_effect that checks the filename
        real_open = open

        def side_effect(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if str(file) == file_path and "rb" in mode:
                raise PermissionError("Access denied")
            return real_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=side_effect):
            # Should not crash, just skip the file
            hash_val = calculate_static_hash(tmp_dir)
            assert len(hash_val) == 8
