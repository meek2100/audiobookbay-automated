# File: tests/functional/test_diagnostics.py
"""Tests for the diagnostics endpoints and dashboard."""

from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient

from audiobook_automated.extensions import torrent_manager


def test_diagnostics_disabled_by_default(app: Flask, client: FlaskClient) -> None:
    """Ensure diagnostics routes return 404 when disabled."""
    app.config["ENABLE_DIAGNOSTICS"] = False
    app.config["FLASK_DEBUG"] = False
    app.config["TESTING"] = False

    resp = client.get("/diagnostics")
    assert resp.status_code == 404

    resp_health = client.get("/api/diagnostics/health")
    assert resp_health.status_code == 404

    resp_inspect = client.get("/api/diagnostics/inspect?query=test")
    assert resp_inspect.status_code == 404


def test_diagnostics_dashboard_enabled(app: Flask, client: FlaskClient) -> None:
    """Ensure diagnostics dashboard renders successfully when enabled."""
    app.config["ENABLE_DIAGNOSTICS"] = True
    resp = client.get("/diagnostics")
    assert resp.status_code == 200
    assert b"System Diagnostics" in resp.data
    assert b"Live Parser & Metadata Inspector" in resp.data


def test_diagnostics_health_api(app: Flask, client: FlaskClient) -> None:
    """Ensure /api/diagnostics/health returns correct JSON structure."""
    app.config["ENABLE_DIAGNOSTICS"] = True

    strat_mock = MagicMock()
    strat_mock.verify_credentials.return_value = True
    strat_fail = MagicMock()
    strat_fail.verify_credentials.side_effect = RuntimeError("Offline client")

    with patch.object(torrent_manager, "clients", {"client1": strat_mock, "client2": strat_fail}):
        with patch("audiobook_automated.scraper.network.check_mirror", return_value="audiobookbay.lu"):
            resp = client.get("/api/diagnostics/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "healthy"
            assert "system" in data
            assert "mirrors" in data
            assert "cache" in data
            assert "clients" in data
            assert len(data["clients"]) == 2
            assert data["clients"][0]["connected"] is True
            assert data["clients"][1]["connected"] is False
            assert "Offline client" in data["clients"][1]["error"]


def test_diagnostics_health_api_resource_exception(app: Flask, client: FlaskClient) -> None:
    """Ensure /api/diagnostics/health handles resource getrusage exceptions gracefully."""
    app.config["ENABLE_DIAGNOSTICS"] = True

    with patch.object(torrent_manager, "clients", {}):
        with patch("resource.getrusage", side_effect=Exception("ru_maxrss error")):
            with patch("audiobook_automated.scraper.network.check_mirror", return_value=None):
                resp = client.get("/api/diagnostics/health")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["system"]["memory_rss_mb"] == 0.0


def test_diagnostics_inspect_missing_params(app: Flask, client: FlaskClient) -> None:
    """Ensure /api/diagnostics/inspect requires url or query."""
    app.config["ENABLE_DIAGNOSTICS"] = True
    resp = client.get("/api/diagnostics/inspect")
    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Either 'url' or 'query' parameter is required"}


def test_diagnostics_inspect_query(app: Flask, client: FlaskClient) -> None:
    """Ensure /api/diagnostics/inspect works for search queries."""
    app.config["ENABLE_DIAGNOSTICS"] = True

    mock_results = [{"title": "Test Book", "link": "/abss/test/"}]
    with patch("audiobook_automated.scraper.core.search_audiobookbay", return_value=mock_results):
        resp = client.get("/api/diagnostics/inspect?query=Test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["type"] == "search"
        assert data["count"] == 1
        assert data["data"] == mock_results


def test_diagnostics_inspect_url(app: Flask, client: FlaskClient) -> None:
    """Ensure /api/diagnostics/inspect works for book detail URLs."""
    app.config["ENABLE_DIAGNOSTICS"] = True

    mock_details = {"title": "Inspect Book", "category": ["Teens & Young Adults"]}
    with patch("audiobook_automated.scraper.core.get_book_details", return_value=mock_details):
        resp = client.get("/api/diagnostics/inspect?url=/abss/test-book/")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["type"] == "details"
        assert data["data"]["title"] == "Inspect Book"
        assert data["data"]["category"] == ["Teens & Young Adults"]


def test_diagnostics_inspect_url_not_found(app: Flask, client: FlaskClient) -> None:
    """Ensure /api/diagnostics/inspect handles missing/failed details."""
    app.config["ENABLE_DIAGNOSTICS"] = True

    with patch("audiobook_automated.scraper.core.get_book_details", return_value=None):
        resp = client.get("/api/diagnostics/inspect?url=/abss/missing/")
        assert resp.status_code == 404
        assert "Failed to retrieve book details" in resp.get_json()["error"]


def test_diagnostics_inspect_exception(app: Flask, client: FlaskClient) -> None:
    """Ensure /api/diagnostics/inspect handles internal scraping exceptions gracefully."""
    app.config["ENABLE_DIAGNOSTICS"] = True

    with patch("audiobook_automated.scraper.core.search_audiobookbay", side_effect=RuntimeError("Scraper boom")):
        resp = client.get("/api/diagnostics/inspect?query=crash")
        assert resp.status_code == 500
        assert resp.get_json() == {"error": "Scraper boom"}


def test_diagnostics_logs_endpoints(app: Flask, client: FlaskClient) -> None:
    """Ensure /api/diagnostics/logs and download work correctly."""
    app.config["ENABLE_DIAGNOSTICS"] = True
    app.logger.info("Test log entry for diagnostics endpoint")

    # JSON logs endpoint
    resp = client.get("/api/diagnostics/logs?limit=5")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "logs" in data
    assert data["count"] > 0

    # Invalid limit defaults gracefully
    resp_invalid = client.get("/api/diagnostics/logs?limit=notanumber")
    assert resp_invalid.status_code == 200

    # Download logs endpoint
    resp_dl = client.get("/api/diagnostics/logs/download")
    assert resp_dl.status_code == 200
    assert resp_dl.mimetype == "text/plain"
    assert "Content-Disposition" in resp_dl.headers
    assert "audiobookbay-automated-logs.txt" in resp_dl.headers["Content-Disposition"]
    assert b"Test log entry for diagnostics endpoint" in resp_dl.data
