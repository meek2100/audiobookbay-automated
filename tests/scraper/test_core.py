# File: tests/scraper/test_core.py
"""Unit tests for core scraping logic."""

import concurrent.futures
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from flask import Flask

from audiobook_automated.scraper.core import fetch_page_results, get_search_url, search_audiobookbay


def test_fetch_page_results_unexpected_exception() -> None:
    """Test that unexpected exceptions are handled."""
    mock_session = MagicMock()
    mock_session.get.side_effect = ValueError("Something unexpected")

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            # Patch logging.getLogger to capture the logger instance
            with patch("logging.getLogger") as mock_get_logger:
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger

                results = fetch_page_results("http://example.com")
                assert results == []


def test_fetch_page_missing_href() -> None:
    """Test fetch_page_results handles post title missing href attribute gracefully."""
    html_content = """
    <html>
        <body>
            <div class="post">
                <div class="postTitle">
                    <h2><a>Title Without Href</a></h2>
                </div>
                <div class="postContent">
                    <img src="/cover.jpg" />
                    Some content
                </div>
                <div class="postInfo">Info</div>
            </div>
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.text = html_content
    mock_response.raise_for_status = MagicMock()

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response

    with patch("audiobook_automated.scraper.core.network.get_session", return_value=mock_session):
        with patch("audiobook_automated.scraper.core.network.get_semaphore"):
            results = fetch_page_results("http://audiobookbay.lu/page/1/?s=query")
            assert results == []


def test_search_partial_failure() -> None:
    """Test that search continues and clears cache if one page fails but others succeed."""
    success_result = [
        {
            "title": "Book 1",
            "link": "http://link1",
            "cover": None,
            "language": "En",
            "category": "Audio",
            "post_date": "2024",
            "format": "MP3",
            "bitrate": "128",
            "file_size": "100MB",
        }
    ]

    future_success: concurrent.futures.Future[list[dict[str, Any]]] = concurrent.futures.Future()
    future_success.set_result(success_result)

    future_failure: concurrent.futures.Future[list[dict[str, Any]]] = concurrent.futures.Future()
    future_failure.set_exception(requests.HTTPError("500 Server Error"))

    with patch("audiobook_automated.extensions.executor") as mock_executor:
        mock_executor.submit.side_effect = [future_success, future_failure]

        with patch("audiobook_automated.scraper.core.network.find_best_mirror", return_value="audiobookbay.lu"):
            with patch("audiobook_automated.scraper.core.network.mirror_cache") as mock_mirror_cache:
                mock_mirror_cache.__contains__.return_value = True

                results = search_audiobookbay("test_query", max_pages=2)

                assert len(results) == 1
                assert results[0]["title"] == "Book 1"
                mock_mirror_cache.__delitem__.assert_called_with("active_mirror")


def test_search_total_failure() -> None:
    """Test that search returns empty list when no mirrors found."""
    with patch("audiobook_automated.scraper.core.network.find_best_mirror", return_value=None):
        results = search_audiobookbay("query")
        assert results == []


def test_search_pagination_cancellation(app: Flask) -> None:
    """Test that pagination stops and futures are cancelled when a page returns no results."""
    mock_future1 = MagicMock()
    mock_future1.result.return_value = [{"title": "Book 1", "link": "http://link1"}]

    mock_future2 = MagicMock()
    mock_future2.result.return_value = []

    mock_future3 = MagicMock()
    mock_future3.result.return_value = []

    with (
        app.app_context(),
        patch("audiobook_automated.extensions.executor.submit") as mock_submit,
        patch("audiobook_automated.scraper.core.network.find_best_mirror", return_value="mirror.com"),
        patch("audiobook_automated.scraper.core.network.get_session"),
    ):
        mock_submit.side_effect = [mock_future1, mock_future2, mock_future3]

        results = search_audiobookbay("test", max_pages=3)

        assert len(results) == 1
        assert results[0]["title"] == "Book 1"


def test_search_http_error_invalidation() -> None:
    """Test that search invalidates mirror on HTTPError."""
    future_failure: concurrent.futures.Future[Any] = concurrent.futures.Future()
    future_failure.set_exception(requests.HTTPError("502 Bad Gateway"))

    with patch("audiobook_automated.extensions.executor") as mock_executor:
        mock_executor.submit.return_value = future_failure
        with patch("audiobook_automated.scraper.core.network.find_best_mirror", return_value="mirror.com"):
            with patch("audiobook_automated.scraper.core.network.mirror_cache") as mock_mirror_cache:
                mock_mirror_cache.__contains__.return_value = True

                results = search_audiobookbay("test_query", max_pages=1)
                assert results == []
                mock_mirror_cache.__delitem__.assert_called_with("active_mirror")
