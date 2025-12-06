from typing import Any
from unittest.mock import patch


def test_home_page_load(client: Any) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b"Search AudiobookBay" in response.data


def test_search_via_get(client: Any) -> None:
    with patch("app.routes.search_audiobookbay", return_value=[{"title": "Book 1"}]) as mock_search:
        response = client.get("/?query=test")
        assert response.status_code == 200
        assert b"Book 1" in response.data
        mock_search.assert_called_with("test")


def test_search_whitespace_query(client: Any) -> None:
    with patch("app.routes.search_audiobookbay") as mock_search:
        response = client.get("/?query=%20%20%20")
        assert response.status_code == 200
        mock_search.assert_not_called()
        assert b"Search AudiobookBay" in response.data


def test_search_exception_handling(client: Any) -> None:
    with patch("app.routes.search_audiobookbay") as mock_search:
        mock_search.side_effect = Exception("Connection timed out")
        response = client.get("/?query=my+book")
        assert response.status_code == 200
        assert b"Search Failed: Connection timed out" in response.data


def test_details_route_success(client: Any) -> None:
    fake_details = {"title": "Detailed Book", "description": "<p>Desc</p>"}
    with patch("app.routes.get_book_details", return_value=fake_details):
        response = client.get("/details?link=http://book.com")
        assert response.status_code == 200
        assert b"Detailed Book" in response.data


def test_details_route_failure(client: Any) -> None:
    with patch("app.routes.get_book_details", side_effect=Exception("Scrape Error")):
        response = client.get("/details?link=http://book.com")
        assert response.status_code == 200
        assert b"Could not load details" in response.data


def test_details_route_missing_link(client: Any) -> None:
    response = client.get("/details")
    assert response.status_code == 302
    assert "/" in response.location
