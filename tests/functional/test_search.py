# File: tests/functional/test_search.py
"""Functional tests for the search routes and search logic."""

from typing import Any
from unittest.mock import patch


def test_home_page_load(client: Any) -> None:
    """Test that the home page loads successfully and displays the search form."""
    response = client.get("/")
    assert response.status_code == 200
    # Updated text to match new "The Crow's Nest" branding in template
    assert b"Search The Crow's Nest" in response.data


def test_search_via_get(client: Any) -> None:
    """Test performing a search via a standard GET request with query parameters."""
    with patch("audiobook_automated.routes.search_audiobookbay", return_value=[{"title": "Book 1"}]) as mock_search:
        response = client.get("/?query=test")
        assert response.status_code == 200
        assert b"Book 1" in response.data
        mock_search.assert_called_with("test")


def test_search_short_query(client: Any) -> None:
    """Test that a search query shorter than 2 characters triggers an error."""
    with patch("audiobook_automated.routes.search_audiobookbay") as mock_search:
        response = client.get("/?query=a")
        assert response.status_code == 200
        assert b"Search query must be at least 2 characters long." in response.data
        mock_search.assert_not_called()


def test_search_whitespace_query(client: Any) -> None:
    """Test that a query consisting only of whitespace is ignored."""
    with patch("audiobook_automated.routes.search_audiobookbay") as mock_search:
        response = client.get("/?query=%20%20%20")
        assert response.status_code == 200
        mock_search.assert_not_called()
        # Updated text to match new "The Crow's Nest" branding in template
        assert b"Search The Crow's Nest" in response.data


def test_search_exception_handling(client: Any) -> None:
    """Test that generic exceptions during search are caught and displayed to the user."""
    with patch("audiobook_automated.routes.search_audiobookbay") as mock_search:
        mock_search.side_effect = Exception("Generic error")
        response = client.get("/?query=my+book")
        assert response.status_code == 200
        assert b"Search Failed: Generic error" in response.data


def test_search_connection_error(client: Any) -> None:
    """Test specific handling of ConnectionError during search.

    This covers the explicit exception handler added to routes.py for
    user-friendly error messages when mirrors are down.
    """
    with patch("audiobook_automated.routes.search_audiobookbay") as mock_search:
        mock_search.side_effect = ConnectionError("No mirrors reachable")
        response = client.get("/?query=test")
        assert response.status_code == 200
        # Verify the user-friendly message is displayed
        assert b"Could not connect to AudiobookBay mirrors" in response.data


def test_details_route_success(client: Any) -> None:
    """Test that the details page loads correctly when a valid link is provided."""
    fake_details = {"title": "Detailed Book", "description": "<p>Desc</p>"}
    with patch("audiobook_automated.routes.get_book_details", return_value=fake_details):
        response = client.get("/details?link=http://book.com")
        assert response.status_code == 200
        assert b"Detailed Book" in response.data


def test_details_route_failure(client: Any) -> None:
    """Test that the details page handles scraping errors gracefully."""
    with patch("audiobook_automated.routes.get_book_details", side_effect=Exception("Scrape Error")):
        response = client.get("/details?link=http://book.com")
        assert response.status_code == 200
        assert b"Could not load details" in response.data


def test_details_route_missing_link(client: Any) -> None:
    """Test that accessing /details without a link parameter redirects to home."""
    response = client.get("/details")
    assert response.status_code == 302
    assert "/" in response.location
