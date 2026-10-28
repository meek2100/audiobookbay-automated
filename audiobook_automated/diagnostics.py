# File: audiobook_automated/diagnostics.py
"""Diagnostics module providing real-time system, network, scraper, and client diagnostics.

Disabled by default in production. Enabled via ENABLE_DIAGNOSTICS=true or FLASK_DEBUG=true.
"""

from __future__ import annotations

import logging
import os
import platform
import resource
import time
from typing import Any

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request

from audiobook_automated.extensions import torrent_manager
from audiobook_automated.logging_buffer import log_ring_buffer
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


def _collect_system_info() -> dict[str, Any]:
    """Collect platform, python, process and memory RSS metrics."""
    try:
        memory_usage_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)
    except Exception:
        memory_usage_mb = 0.0

    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "pid": os.getpid(),
        "memory_rss_mb": memory_usage_mb,
    }


def _probe_candidate_mirrors(candidate_mirrors: list[str]) -> list[dict[str, Any]]:
    """Probe candidate mirrors and return latency and scoring statistics."""
    mirror_results: list[dict[str, Any]] = []
    for mirror in candidate_mirrors:
        m_start = time.perf_counter()
        active = network.check_mirror(mirror) is not None
        latency_ms = round((time.perf_counter() - m_start) * 1000, 2)
        stat = network.get_mirror_stat(mirror)
        mirror_results.append(
            {
                "hostname": mirror,
                "reachable": active,
                "latency_ms": latency_ms,
                "ema_latency_ms": stat.ema_latency_ms,
                "success_rate": round(stat.success_rate * 100, 1),
                "cooling_down": stat.is_cooling_down,
                "score": round(stat.score, 1),
                "protocol": stat.protocol,
                "is_parked": stat.is_parked_or_invalid,
            }
        )
    return mirror_results


def _get_strategy_status(strategy_inst: Any, connected: bool, error_msg: str | None) -> str:
    """Determine friendly status label for a torrent client strategy."""
    if connected:
        return "Connected"
    if getattr(strategy_inst, "is_ip_banned", False) is True:
        return "IP Banned"
    cooldown = getattr(strategy_inst, "auth_cooldown_until", 0)
    if isinstance(cooldown, (int, float)) and cooldown > time.time():
        return "Auth Cooldown"
    if error_msg:
        return "Auth Failed"
    return "Disconnected"


def _collect_client_diagnostics(manager: Any) -> list[dict[str, Any]]:
    """Check connectivity and collect detailed diagnostics for configured download clients."""
    clients_info: list[dict[str, Any]] = []
    configured_clients = getattr(manager, "clients", {})
    if configured_clients:
        for name, strategy_inst in configured_clients.items():
            c_start = time.perf_counter()
            try:
                connected = bool(strategy_inst.verify_credentials())
                raw_err = getattr(strategy_inst, "last_auth_error", None)
                c_err = str(raw_err) if raw_err is not None else None
            except Exception as e:
                connected = False
                c_err = str(e)
            c_status_label = _get_strategy_status(strategy_inst, connected, c_err)
            c_latency = round((time.perf_counter() - c_start) * 1000, 2)
            clients_info.append(
                {
                    "name": name,
                    "connected": connected,
                    "status": c_status_label,
                    "latency_ms": c_latency,
                    "error": c_err,
                }
            )
    else:
        connected = bool(manager.verify_credentials())
        primary_strat = getattr(manager, "strategy", None)
        c_err_str: str | None = None
        if primary_strat:
            raw_err = getattr(primary_strat, "last_auth_error", None)
            c_err_str = str(raw_err) if raw_err is not None else None
        c_status = _get_strategy_status(primary_strat, connected, c_err_str)

        clients_info.append(
            {
                "name": current_app.config.get("DL_CLIENT", "default"),
                "connected": connected,
                "status": c_status,
                "error": c_err_str,
            }
        )
    return clients_info


@diagnostics_bp.route("/api/diagnostics/health")
def diagnostics_health() -> Response:
    """Return JSON system health, mirror status, cache metrics, and client connectivity."""
    t0 = time.perf_counter()

    sys_info = _collect_system_info()
    candidate_mirrors = network.get_mirrors()[:8]
    mirror_results = _probe_candidate_mirrors(candidate_mirrors)

    with network.CACHE_LOCK:
        active_mirror = network.mirror_cache.get("active_mirror")
        negative_cache_active = "failure" in network.failure_cache
        details_cache_size = len(network.details_cache)
        details_cache_max = network.details_cache.maxsize
    top_search_mirrors = network.get_active_search_mirrors(limit=3)
    if not active_mirror and top_search_mirrors:
        active_mirror = top_search_mirrors[0]

    clients_info = _collect_client_diagnostics(torrent_manager)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return jsonify(
        {
            "status": "healthy",
            "diagnostics_elapsed_ms": elapsed_ms,
            "system": sys_info,
            "mirrors": {
                "active_mirror": active_mirror,
                "negative_cache_active": negative_cache_active,
                "top_search_mirrors": top_search_mirrors,
                "mirrors": mirror_results,
            },
            "cache": {
                "details_cache_size": details_cache_size,
                "details_cache_max": details_cache_max,
            },
            "clients": clients_info,
        }
    )


@diagnostics_bp.route("/api/diagnostics/logs")
def diagnostics_logs() -> Response:
    """Return recent sanitized application logs as JSON."""
    limit_str = request.args.get("limit", "100")
    try:
        limit = int(limit_str)
    except ValueError:
        limit = 100

    logs = log_ring_buffer.get_logs(limit=limit)
    return jsonify({"logs": logs, "count": len(logs)})


@diagnostics_bp.route("/api/diagnostics/logs/download")
def diagnostics_logs_download() -> Response:
    """Download recent sanitized logs as a text file."""
    text_content = log_ring_buffer.get_text_logs()
    return Response(
        text_content,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=audiobookbay-automated-logs.txt"},
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
