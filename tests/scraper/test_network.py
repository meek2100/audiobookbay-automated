# tests/scraper/test_network.py
import os
from typing import Any, Generator
from unittest.mock import MagicMock, mock_open, patch

import pytest
import requests

from app.constants import DEFAULT_TRACKERS, USER_AGENTS
from app.scraper import network


@pytest.fixture  # type: ignore[untyped-decorator]
def mock_app_context() -> Generator[MagicMock, None, None]:
    """Fixture to mock current_app.config for network functions."""
    with patch("app.scraper.network.current_app") as mock_app:
        mock_app.config = {}
        yield mock_app


def test_get_trackers_from_env(mock_app_context: Any) -> None:
    # Clear cache before test
    network.get_trackers.cache_clear()

    mock_app_context.config["MAGNET_TRACKERS"] = ["udp://env.tracker:1337"]

    trackers = network.get_trackers()
    assert len(trackers) == 1
    assert trackers[0] == "udp://env.tracker:1337"


def test_get_trackers_from_json(mock_app_context: Any) -> None:
    network.get_trackers.cache_clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []  # Empty env

    with patch.dict(os.environ, {}, clear=True):
        mock_data = '["udp://json.tracker:80"]'
        with patch("builtins.open", mock_open(read_data=mock_data)):
            with patch("os.path.exists", return_value=True):
                trackers = network.get_trackers()
                assert trackers == ["udp://json.tracker:80"]


def test_get_trackers_defaults(mock_app_context: Any) -> None:
    network.get_trackers.cache_clear()
    mock_app_context.config["MAGNET_TRACKERS"] = []

    with patch("os.path.exists", return_value=False):
        trackers = network.get_trackers()
        assert trackers == DEFAULT_TRACKERS


def test_get_mirrors_logic(mock_app_context: Any) -> None:
    """Test combining user config with defaults and deduplication."""
    mock_app_context.config["ABB_HOSTNAME"] = "primary.com"
    mock_app_context.config["ABB_MIRRORS"] = ["mirror1.com", "primary.com"]  # Duplicate primary

    mirrors = network.get_mirrors()

    # Order: Primary -> Extra -> Defaults
    assert mirrors[0] == "primary.com"
    assert mirrors[1] == "mirror1.com"
    assert "audiobookbay.lu" in mirrors
    # Ensure primary only appears once despite being in extra list
    assert mirrors.count("primary.com") == 1


def test_check_mirror_success_head() -> None:
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.return_value.status_code = 200
        result = network.check_mirror("good.mirror")
        assert result == "good.mirror"


def test_check_mirror_success_get_fallback() -> None:
    """Test fallback to GET if HEAD raises an exception."""
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.side_effect = requests.RequestException("Method Not Allowed")
        with patch("app.scraper.network.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            result = network.check_mirror("fallback.mirror")
            assert result == "fallback.mirror"


def test_check_mirror_head_500_fallback() -> None:
    """Test fallback to GET if HEAD returns a non-200 status."""
    with patch("app.scraper.network.requests.head") as mock_head:
        mock_head.return_value.status_code = 500
        with patch("app.scraper.network.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            result = network.check_mirror("flaky.mirror")
            assert result == "flaky.mirror"


def test_find_best_mirror_all_fail(mock_app_context: Any) -> None:
    network.mirror_cache.clear()
    with patch("app.scraper.network.check_mirror", return_value=None):
        result = network.find_best_mirror()
        assert result is None


def test_find_best_mirror_success(mock_app_context: Any) -> None:
    network.mirror_cache.clear()
    # Mock get_mirrors to return a controlled list
    with patch("app.scraper.network.get_mirrors", return_value=["mirror1.com"]):
        with patch("app.scraper.network.check_mirror", side_effect=["mirror1.com"]):
            result = network.find_best_mirror()
            assert result == "mirror1.com"


def test_get_random_user_agent_returns_string() -> None:
    ua = network.get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 10
    assert ua in USER_AGENTS
