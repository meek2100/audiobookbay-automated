from app.utils import sanitize_title


def test_sanitize_simple_title():
    assert sanitize_title("Harry Potter") == "Harry Potter"


def test_sanitize_special_chars():
    # Colons and slashes should be removed
    assert sanitize_title("Book: The Movie / Part 1") == "Book The Movie  Part 1"


def test_sanitize_windows_reserved():
    # Trailing periods and spaces are bad in Windows
    assert sanitize_title("The End. ") == "The End"


def test_sanitize_empty():
    """Test that explicit empty/None inputs fallback to Unknown_Title."""
    assert sanitize_title("") == "Unknown_Title"
    assert sanitize_title(None) == "Unknown_Title"


def test_sanitize_strips_to_empty():
    """Test that a title composed only of illegal chars falls back safely."""
    # A title like "..." cleans to "" then strips to "", so we need a fallback.
    assert sanitize_title("...") == "Unknown_Title"
    assert sanitize_title("???") == "Unknown_Title"
