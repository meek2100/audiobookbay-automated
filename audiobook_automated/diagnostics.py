# File: audiobook_automated/diagnostics.py
"""Diagnostics module providing real-time system, network, scraper, and client diagnostics.

Disabled by default in production. Enabled via ENABLE_DIAGNOSTICS=true or FLASK_DEBUG=true.
"""

from __future__ import annotations

import logging
import os
import platform
import time
from typing import Any

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request

from audiobook_automated.extensions import torrent_manager
from audiobook_automated.scraper import core, network

logger = logging.getLogger(__name__)

diagnostics_bp = Blueprint("diagnostics", __name__)


def is_diagnostics_enabled() -> bool:
    """Check if diagnostics are enabled via config or debug mode."""
    return bool(
        current_app.config.get("ENABLE_DIAGNOSTICS", False)
        or current_app.config.get("FLASK_DEBUG", False)
        or current_app.config.get("TESTING", False)
    )


@diagnostics_bp.before_request
def check_diagnostics_enabled() -> None:
    """Abort with 404 Not Found if diagnostics are disabled."""
    if not is_diagnostics_enabled():
        abort(404)


@diagnostics_bp.route("/diagnostics")
def diagnostics_page() -> str:
    """Render the diagnostics dashboard."""
    return render_template(
        "diagnostics.html",
        active_endpoint="diagnostics.diagnostics_page",
    )


@diagnostics_bp.route("/api/diagnostics/health")
def diagnostics_health() -> Response:
    """Return JSON system health, mirror status, cache metrics, and client connectivity."""
    t0 = time.perf_counter()

    # 1. System & Environment Metrics
    try:
        import resource

        memory_usage_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)
    except Exception:
        memory_usage_mb = 0.0

    sys_info = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "pid": os.getpid(),
        "memory_rss_mb": memory_usage_mb,
    }

    # 2. Mirror Status & Ping
    all_mirrors = network.get_mirrors()
    mirror_results: list[dict[str, Any]] = []

    for mirror in all_mirrors:
        m_start = time.perf_counter()
        active = network.check_mirror(mirror) is not None
        latency_ms = round((time.perf_counter() - m_start) * 1000, 2)
        mirror_results.append(
            {
                "hostname": mirror,
                "reachable": active,
                "latency_ms": latency_ms,
            }
        )

    with network.CACHE_LOCK:
        active_mirror = network.mirror_cache.get("active_mirror")
        negative_cache_active = "failure" in network.failure_cache
        details_cache_size = len(network.details_cache)
        details_cache_max = network.details_cache.maxsize

    # 3. Torrent Clients Status
    clients_info: list[dict[str, Any]] = []
    configured_clients = getattr(torrent_manager, "clients", {})
    if configured_clients:
        for name, strat in configured_clients.items():
            c_start = time.perf_counter()
            try:
                connected = bool(strat.verify_credentials())
                c_err = None
            except Exception as e:
                connected = False
                c_err = str(e)
            c_latency = round((time.perf_counter() - c_start) * 1000, 2)
            clients_info.append(
                {
                    "name": name,
                    "connected": connected,
                    "latency_ms": c_latency,
                    "error": c_err,
                    "strategy_class": strat.__class__.__name__,
                }
            )
    else:
        connected = bool(torrent_manager.verify_credentials())
        clients_info.append(
            {
                "name": current_app.config.get("DL_CLIENT", "default"),
                "connected": connected,
                "strategy_class": torrent_manager.strategy.__class__.__name__ if torrent_manager.strategy else None,
            }
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return jsonify(
        {
            "status": "healthy",
            "diagnostics_elapsed_ms": elapsed_ms,
            "system": sys_info,
            "mirrors": {
                "active_mirror": active_mirror,
                "negative_cache_active": negative_cache_active,
                "mirrors": mirror_results,
            },
            "cache": {
                "details_cache_size": details_cache_size,
                "details_cache_max": details_cache_max,
            },
            "clients": clients_info,
        }
    )


@diagnostics_bp.route("/api/diagnostics/inspect")
def diagnostics_inspect() -> Response | tuple[Response, int]:
    """Inspect parser output for a live URL or query to verify tag and metadata fidelity."""
    url = request.args.get("url")
    query = request.args.get("query")

    if not url and not query:
        return jsonify({"error": "Either 'url' or 'query' parameter is required"}), 400

    try:
        if url:
            details = core.get_book_details(url, refresh=True)
            if not details:
                return jsonify({"error": f"Failed to retrieve book details for '{url}'"}), 404
            return jsonify({"type": "details", "url": url, "data": details})

        # Query inspection
        results = core.search_audiobookbay(query or "", max_pages=1)
        return jsonify(
            {
                "type": "search",
                "query": query,
                "count": len(results),
                "data": results,
            }
        )
    except Exception as e:
        logger.error(f"Diagnostics inspect failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
