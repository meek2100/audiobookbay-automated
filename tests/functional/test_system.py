# File: tests/functional/test_system.py
"""Functional tests for system-level routes and static assets."""

from typing import Any
from unittest.mock import MagicMock, patch


def test_health_check_route(client: Any) -> None:
    """Test the /health endpoint returns a 200 OK JSON response."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "client": "connected"}
    assert response.content_type == "application/json"


def test_home_page_static_versioning(client: Any) -> None:
    """Test that static assets in the home page include version query parameters."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"?v=" in response.data
    assert b"favicon.ico?v=" in response.data


def test_static_assets_cache_control(client: Any) -> None:
    """Test that static assets are served with long-term caching headers."""
    response = client.get("/static/images/favicon.ico")
    if response.status_code == 200:
        cache_control = response.headers.get("Cache-Control", "")
        assert "max-age=31536000" in cache_control
        assert "public" in cache_control


def test_nav_link_injection(client: Any) -> None:
    """Test that injected variables correctly appear in the template."""
    # FIX: Update config directly on the app instance, not via module monkeypatch
    client.application.config["NAV_LINK_NAME"] = "My Player"
    client.application.config["NAV_LINK_URL"] = "http://player.local"

    response = client.get("/")
    assert b"My Player" in response.data
    assert b"http://player.local" in response.data


def test_library_reload_injection(client: Any) -> None:
    """Test that the Reload Library link appears only when configured."""
    # Case 1: Configured -> Link should be present
    client.application.config["ABS_URL"] = "http://abs"
    client.application.config["ABS_KEY"] = "key"
    client.application.config["ABS_LIB"] = "lib"
    # FIX: The app calculates this at startup. We must manually update it for the test
    # to simulate the state derived from the env vars above.
    client.application.config["LIBRARY_RELOAD_ENABLED"] = True

    response = client.get("/")
    assert b"Reload Library" in response.data

    # Case 2: Not Configured -> Link should be absent
    client.application.config["ABS_URL"] = None
    # FIX: Manually update to False
    client.application.config["LIBRARY_RELOAD_ENABLED"] = False

    response = client.get("/")
    assert b"Reload Library" not in response.data


def test_status_page(client: Any) -> None:
    """Test that the status page renders active downloads correctly."""
    from audiobook_automated.clients.base import TorrentStatus

    # FIX: Patch where it is imported in routes.py
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = [
            TorrentStatus(id="1", name="Book 1", progress=50, state="Downloading", size="100 MB")
        ]
        response = client.get("/status")
        assert response.status_code == 200
        assert b"Book 1" in response.data


def test_status_route_error(client: Any) -> None:
    """Test that the status page displays errors when the torrent manager fails."""
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.side_effect = Exception("Database Locked")

        response = client.get("/status")
        assert response.status_code == 200
        assert b"Error connecting to client" in response.data
        assert b"Database Locked" in response.data


def test_status_page_empty(client: Any) -> None:
    """Test status page rendering when there are no active torrents.

    Ensures the empty state message matches the UI expectations.
    """
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = []
        response = client.get("/status")
        assert response.status_code == 200
        assert b"No active downloads found" in response.data


def test_status_page_json_response(client: Any) -> None:
    """Test that the status page returns JSON when requested.

    This verifies the frontend polling mechanism works (fixes the hermeneutic gap
    between frontend expectations and backend delivery).
    """
    from audiobook_automated.clients.base import TorrentStatus

    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.return_value = [
            TorrentStatus(id="1", name="JSON Book", progress=99.9, state="Seeding", size="500 MB")
        ]

        response = client.get("/status?json=1")

        assert response.status_code == 200
        assert response.is_json
        data = response.json
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "JSON Book"


def test_status_page_json_error(client: Any) -> None:
    """Test that status page returns JSON error structure on failure when polling."""
    with patch("audiobook_automated.routes.torrent_manager") as mock_tm:
        mock_tm.get_status.side_effect = Exception("Client unreachable")

        response = client.get("/status?json=1")

        assert response.status_code == 500
        assert response.is_json
        # Explicit check for error key as defined in routes.py
        assert "Client unreachable" in response.json["error"]


def test_reload_library_error(client: Any) -> None:
    """Test that the reload_library endpoint handles upstream errors gracefully."""
    # Ensure the feature is enabled
    client.application.config["LIBRARY_RELOAD_ENABLED"] = True
    client.application.config["ABS_URL"] = "http://abs"
    client.application.config["ABS_KEY"] = "key"
    client.application.config["ABS_LIB"] = "lib"

    # Mock requests.post to raise an error or return non-200
    with patch("audiobook_automated.routes.requests.post") as mock_post:
        # Simulate a 500 error from Audiobookshelf
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        # We need to wait for the background task if it's threaded.
        # However, the route itself returns 200 immediately saying "Scan triggered".
        # The error handling happens in the background thread (executor).
        # To test the error handling branch, we usually inspect logs or use a synchronous executor.

        # If the route logic puts it in a future, we need to mock the executor to run it synchronously
        # OR just verify the route accepts the request and logs/handles it.

        # Looking at routes.py (in memory): "reload_library endpoint operates asynchronously..."
        # So the route just returns success.
        # BUT the requirement says: "mock a non-200 response for reload_library to cover the error handling branch."
        # This implies we want to verify the background logic handles the 500.

        # To do this, we should invoke the target function directly if possible, or
        # mock the executor to run inline.
        # The route calls `executor.submit(trigger_scan, ...)`

        # Let's mock executor.submit to run the function immediately so we can capture side effects (logging).
        with patch("audiobook_automated.routes.executor") as mock_executor:
            # We define a side effect that executes the function passed to submit
            def run_immediately(fn: Any, *args: Any, **kwargs: Any) -> MagicMock:
                fn(*args, **kwargs)
                return MagicMock()

            mock_executor.submit.side_effect = run_immediately

            with patch("audiobook_automated.routes.logger") as mock_logger:
                response = client.post("/reload_library")
                assert response.status_code == 200

                # Verify that the error was logged
                # We expect something like "ABS Scan failed: 500"
                mock_logger.error.assert_called()
                # Check args of the error call
                args, _ = mock_logger.error.call_args
                assert "ABS Scan failed" in args[0]
                assert "500" in args[0]
