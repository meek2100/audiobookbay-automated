import logging
from unittest.mock import MagicMock, patch

import pytest
import requests
import requests_mock

from app import scraper
from app.scraper import extract_magnet_link, get_book_details, search_audiobookbay


def test_search_audiobookbay_success(mock_sleep):
    with patch("app.scraper.find_best_mirror", return_value="mirror.com"):
        with patch("app.scraper.get_session"):
            with patch("app.scraper.fetch_and_parse_page", return_value=[{"title": "Test Book"}]):
                results = search_audiobookbay("query", max_pages=1)
                assert len(results) == 1
                assert results[0]["title"] == "Test Book"


def test_search_no_mirrors_raises_error(mock_sleep):
    scraper.mirror_cache.clear()
    with patch("app.scraper.find_best_mirror", return_value=None):
        with pytest.raises(ConnectionError) as exc:
            search_audiobookbay("test")
        assert "No reachable AudiobookBay mirrors" in str(exc.value)


def test_search_thread_failure(mock_sleep):
    scraper.search_cache.clear()
    scraper.mirror_cache.clear()
    with patch("app.scraper.find_best_mirror", return_value="mirror.com"):
        with patch("app.scraper.get_session"):
            with patch("app.scraper.fetch_and_parse_page", side_effect=Exception("Scrape Fail")):
                with patch("app.scraper.mirror_cache") as mock_cache:
                    results = search_audiobookbay("query", max_pages=1)
                    assert results == []
                    mock_cache.clear.assert_called()


def test_search_audiobookbay_generic_exception_in_thread(mock_sleep):
    scraper.search_cache.clear()
    scraper.mirror_cache.clear()

    with patch("app.scraper.find_best_mirror", return_value="mirror.com"):
        with patch("app.scraper.get_session"):
            with patch("concurrent.futures.ThreadPoolExecutor") as MockExecutor:
                mock_future = MagicMock()
                mock_future.result.side_effect = ArithmeticError("Unexpected calculation error")
                mock_executor_instance = MockExecutor.return_value.__enter__.return_value
                mock_executor_instance.submit.return_value = mock_future

                with patch("concurrent.futures.as_completed", return_value=[mock_future]):
                    with patch.object(scraper.mirror_cache, "clear") as mock_mirror_clear:
                        with patch.object(scraper.search_cache, "clear") as mock_search_clear:
                            with patch("app.scraper.logger") as mock_logger:
                                results = search_audiobookbay("query", max_pages=1)
                                assert results == []
                                args, _ = mock_logger.error.call_args
                                assert "Page scrape failed" in args[0]
                                mock_mirror_clear.assert_called()
                                mock_search_clear.assert_called()


def test_search_special_characters(real_world_html, mock_sleep):
    hostname = "audiobookbay.lu"
    query = "Batman & Robin [Special Edition]"
    page = 1
    user_agent = "TestAgent/1.0"

    session = requests.Session()
    adapter = requests_mock.Adapter()
    session.mount("https://", adapter)

    adapter.register_uri("GET", f"https://{hostname}/page/{page}/", text=real_world_html, status_code=200)

    results = scraper.fetch_and_parse_page(session, hostname, query, page, user_agent)
    assert len(results) > 0


# --- Get Book Details Tests ---


def test_get_book_details_success(details_html, mock_sleep):
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = details_html
        mock_session.return_value.get.return_value = mock_response

        # Use valid domain to pass SSRF check
        details = get_book_details("https://audiobookbay.lu/valid-book")

        assert details["title"] == "A Game of Thrones"
        assert details["info_hash"] == "eb154ac7886539c4d01eae14908586e336cdb550"
        assert details["file_size"] == "1.37 GBs"
        assert "Spam Link" in details["description"]


def test_get_book_details_failure(mock_sleep):
    with patch("app.scraper.get_session") as mock_session:
        mock_session.return_value.get.side_effect = requests.exceptions.RequestException("Net Down")
        with pytest.raises(requests.exceptions.RequestException):
            get_book_details("https://audiobookbay.lu/fail-book")


def test_get_book_details_empty(mock_sleep):
    with pytest.raises(ValueError) as exc:
        get_book_details("")
    assert "No URL provided" in str(exc.value)


def test_get_book_details_url_parse_error(mock_sleep):
    with patch("app.scraper.urlparse", side_effect=Exception("Boom")):
        with pytest.raises(ValueError) as exc:
            get_book_details("http://anything")
    assert "Invalid URL format" in str(exc.value)


def test_get_book_details_missing_metadata(mock_sleep):
    html = """<div class="post"><div class="postTitle"><h1>Empty Book</h1></div></div>"""
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/empty")
        assert details["language"] == "N/A"
        assert details["format"] == "N/A"


def test_get_book_details_unknown_bitrate_normalization(mock_sleep):
    html = """
    <div class="post">
        <div class="postTitle"><h1>Unknown Bitrate</h1></div>
        <div class="postContent"><p>Bitrate: ?</p></div>
    </div>
    """
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/unknown")
        assert details["bitrate"] == "Unknown"


def test_get_book_details_partial_bitrate(mock_sleep):
    html = """
    <div class="post">
        <div class="postTitle"><h1>Partial Info</h1></div>
        <div class="postContent"><p>Bitrate: 128 Kbps</p></div>
    </div>
    """
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/partial_bitrate")
        assert details["format"] == "N/A"
        assert details["bitrate"] == "128 Kbps"


def test_get_book_details_partial_format(mock_sleep):
    html = """
    <div class="post">
        <div class="postTitle"><h1>Partial Info</h1></div>
        <div class="postContent"><p>Format: MP3</p></div>
    </div>
    """
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/partial")
        assert details["format"] == "MP3"
        assert details["bitrate"] == "N/A"


def test_get_book_details_content_without_metadata_labels(mock_sleep):
    html = """
    <div class="post">
        <div class="postTitle"><h1>No Metadata</h1></div>
        <div class="postContent"><p>Just text.</p></div>
    </div>
    """
    with patch("app.scraper.get_session") as mock_session:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_session.return_value.get.return_value = mock_response

        details = get_book_details("https://audiobookbay.lu/no_meta")
        assert details["format"] == "N/A"


# --- Extract Magnet Link Tests ---


def test_extract_magnet_success_table(mock_sleep):
    url = "http://valid.url/book"
    html_content = """
    <html><body><table>
        <tr><td>Info Hash:</td><td>  abc123hash456  </td></tr>
        <tr><td>Trackers:</td><td>http://tracker.com/announce</td></tr>
    </table></body></html>
    """
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_session.get.return_value = mock_response

        with patch("app.scraper.DEFAULT_TRACKERS", []):
            magnet, error = extract_magnet_link(url)
            assert error is None
            assert "magnet:?xt=urn:btih:abc123hash456" in magnet


def test_extract_magnet_regex_fallback(mock_sleep):
    url = "http://fake.url"
    html_content = """<html><body><p>Hash: aaaaaaaaaabbbbbbbbbbccccccccccdddddddddd</p></body></html>"""
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_session.get.return_value = mock_response

        magnet, error = extract_magnet_link(url)
        assert magnet is not None


def test_extract_magnet_missing_info_hash(mock_sleep):
    url = "http://fake.url"
    html_content = """<html><body><p>No hash here</p></body></html>"""
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_session.get.return_value = mock_response

        magnet, error = extract_magnet_link(url)
        assert magnet is None
        assert "Info Hash could not be found" in error


def test_extract_magnet_bad_url(mock_sleep):
    res, err = extract_magnet_link("")
    assert res is None
    assert "No URL" in err
    res, err = extract_magnet_link("not-a-url")
    assert res is None
    assert "Invalid URL" in err


def test_extract_magnet_malformed_url_exception(mock_sleep):
    with patch("app.scraper.urlparse", side_effect=Exception("Parse Error")):
        res, err = extract_magnet_link("http://some.url")
        assert res is None
        assert "Malformed URL" in err


def test_extract_magnet_http_error_code(mock_sleep):
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_session.get.return_value = mock_response

        magnet, error = extract_magnet_link("http://valid.url")
        assert magnet is None
        assert "Status Code: 500" in error


def test_extract_magnet_network_error(mock_sleep, caplog):
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_session.get.side_effect = Exception("Network Down")

        with caplog.at_level(logging.DEBUG):
            magnet, error = extract_magnet_link("http://valid.url")

        assert magnet is None
        assert "Network Down" in error
        assert "Closing scraper session" in caplog.text


def test_extract_magnet_bs4_error(mock_sleep):
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>"
        mock_session.get.return_value = mock_response

        with patch("app.scraper.BeautifulSoup", side_effect=Exception("Parse Fail")):
            magnet, error = extract_magnet_link("http://valid.url")
            assert magnet is None
            assert "Parse Fail" in error


def test_extract_magnet_link_generic_exception(mock_sleep):
    """Tests the generic catch-all block in extract_magnet_link."""
    url = "http://valid.url"
    with patch("app.scraper.get_session") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_session.get.side_effect = ValueError("Generic parsing logic failure")

        with patch("app.scraper.logger") as mock_logger:
            magnet, error = extract_magnet_link(url)
            assert magnet is None
            assert "Generic parsing logic failure" in error
            assert mock_logger.error.called
