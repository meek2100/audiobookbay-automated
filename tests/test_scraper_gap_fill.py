from unittest.mock import MagicMock, patch

from app import scraper


def test_search_audiobookbay_generic_exception_in_thread():
    """
    Tests that the system robustly handles generic runtime errors (e.g. ArithmeticError)
    occurring within a scraper thread. It verifies that caches are cleared to prevent
    corrupt state, ensuring the system resets for the next request.
    """
    # Clear caches to ensure clean state
    scraper.search_cache.clear()
    scraper.mirror_cache.clear()

    # Mock finding a mirror so we proceed to the thread pool execution
    with patch("app.scraper.find_best_mirror", return_value="mirror.com"):
        with patch("app.scraper.get_session"):
            # Mock the executor to return a future that raises a generic Exception
            with patch("concurrent.futures.ThreadPoolExecutor") as MockExecutor:
                mock_future = MagicMock()
                # The future.result() call happens inside the as_completed loop
                mock_future.result.side_effect = ArithmeticError("Unexpected calculation error")

                mock_executor_instance = MockExecutor.return_value.__enter__.return_value
                mock_executor_instance.submit.return_value = mock_future

                # as_completed must yield our mock future so the loop runs
                with patch("concurrent.futures.as_completed", return_value=[mock_future]):
                    # Spy on the cache to verify it was cleared
                    with patch.object(scraper.mirror_cache, "clear") as mock_mirror_clear:
                        with patch.object(scraper.search_cache, "clear") as mock_search_clear:
                            # Spy on logger to ensure we hit the except block
                            with patch("app.scraper.logger") as mock_logger:
                                results = scraper.search_audiobookbay("query", max_pages=1)

                                # Assertions
                                assert results == []
                                # Verify the logger caught the specific exception
                                args, _ = mock_logger.error.call_args
                                assert "Page scrape failed" in args[0]
                                assert "Unexpected calculation error" in str(args[0])

                                # Verify cache clearing
                                mock_mirror_clear.assert_called()
                                mock_search_clear.assert_called()


def test_extract_magnet_link_generic_exception():
    """
    Tests the generic catch-all block in extract_magnet_link.
    Existing tests cover network errors (RequestException), but this ensures
    logic errors (like ValueError during data processing) are also caught safely.
    """
    url = "http://valid.url"

    # Mock get_session to return a mock that raises a generic Python error
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        # Use a non-network exception to hit the generic 'except Exception' block
        mock_session.get.side_effect = ValueError("Generic parsing logic failure")

        with patch("app.scraper.logger") as mock_logger:
            magnet, error = scraper.extract_magnet_link(url)

            assert magnet is None
            assert "Generic parsing logic failure" in error
            # Verify we hit the logger.error line
            assert mock_logger.error.called
