# File: tests/scraper/test_network_malformed.py
"""Test suite for Network module handling malformed trackers."""

import json
from unittest.mock import patch

from audiobook_automated.constants import DEFAULT_TRACKERS
from audiobook_automated.scraper.network import CACHE_LOCK, get_trackers, tracker_cache


def test_malformed_trackers_json(app):
    """Test that get_trackers handles a malformed trackers.json file gracefully."""
    # Clear cache to force reload
    with CACHE_LOCK:
        tracker_cache.clear()

    # Ensure config doesn't override
    app.config["MAGNET_TRACKERS"] = []

    # Mock Path to point to a temporary file we control, or mock open/exists
    with patch("audiobook_automated.scraper.network.Path") as mock_path_cls:
        # We need to mock the sequence:
        # base_dir = Path(__file__).resolve().parents[2]
        # json_path = base_dir / "trackers.json"

        mock_path_instance = mock_path_cls.return_value  # resolve()
        mock_path_instance.resolve.return_value.parents = [None, None, mock_path_instance]  # parents[2]

        # When / "trackers.json" is called
        mock_json_path = mock_path_instance.__truediv__.return_value
        mock_json_path.exists.return_value = True

        # Mock open to return invalid JSON (actually valid JSON but invalid structure as per code expectation "list")
        # Code says: if isinstance(data, list). So we return a dict.
        with patch("builtins.open", new_callable=lambda: patch("builtins.open").start()) as mock_open:
            # We need to actually write valid JSON that is NOT a list to trigger the specific warning
            # "trackers.json contains invalid data (expected a list). Using defaults."
            mock_file = mock_open.return_value.__enter__.return_value
            mock_file.read.return_value = '{"not": "a list"}'

            # Since json.load reads from the file object, we can mock json.load directly or the file read
            with patch("json.load") as mock_json_load:
                mock_json_load.return_value = {"not": "a list"}

                trackers = get_trackers()

                assert trackers == DEFAULT_TRACKERS
                # Verify we hit the specific path? We can check logs if we want, but return value is key.


def test_json_load_exception(app):
    """Test that get_trackers handles JSONDecodeError or other exceptions."""
    with CACHE_LOCK:
        tracker_cache.clear()

    app.config["MAGNET_TRACKERS"] = []

    with patch("audiobook_automated.scraper.network.Path") as mock_path_cls:
        mock_path_instance = mock_path_cls.return_value
        mock_path_instance.resolve.return_value.parents = [None, None, mock_path_instance]
        mock_json_path = mock_path_instance.__truediv__.return_value
        mock_json_path.exists.return_value = True

        with patch("builtins.open") as mock_open:
            with patch("json.load") as mock_json_load:
                mock_json_load.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)

                trackers = get_trackers()

                assert trackers == DEFAULT_TRACKERS
