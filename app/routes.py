"""Routes module handling all web endpoints."""

import logging
import os
from typing import Any, cast

import requests
from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, url_for

from app.constants import DEFAULT_COVER_FILENAME, FALLBACK_TITLE

from .extensions import limiter, torrent_manager
from .scraper import BookDict, extract_magnet_link, get_book_details, search_audiobookbay
from .utils import sanitize_title

logger = logging.getLogger(__name__)

# Create the Blueprint
main_bp = Blueprint("main", __name__)


@main_bp.context_processor
def inject_global_vars() -> dict[str, Any]:
    """Inject global variables into all templates.

    Uses current_app.config to access settings loaded in config.py.
    """
    # Retrieve the pre-calculated hash from config to avoid disk I/O on every request.
    static_version = current_app.config.get("STATIC_VERSION", "v1")

    # Determine if library reload is enabled based on config
    abs_url = current_app.config.get("ABS_URL")
    abs_key = current_app.config.get("ABS_KEY")
    abs_lib = current_app.config.get("ABS_LIB")
    library_reload_enabled = all([abs_url, abs_key, abs_lib])

    return {
        "nav_link_name": current_app.config.get("NAV_LINK_NAME"),
        "nav_link_url": current_app.config.get("NAV_LINK_URL"),
        "library_reload_enabled": library_reload_enabled,
        "static_version": static_version,
        "default_cover_filename": DEFAULT_COVER_FILENAME,
    }


@main_bp.route("/health")
def health() -> Response:
    """Dedicated health check endpoint."""
    # FIX: Cast jsonify result to Response to satisfy strict return type
    return cast(Response, jsonify({"status": "ok"}))


@main_bp.route("/", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def search() -> str | Response:
    """Handle the search interface."""
    books: list[BookDict] = []
    query = ""
    error_message = None

    try:
        query = request.args.get("query") or request.form.get("query") or ""
        query = query.strip()

        if query:
            # AudiobookBay requires lowercase search terms
            search_query = query.lower()
            logger.info(f"Received search query: '{query}' (normalized to '{search_query}')")
            books = search_audiobookbay(search_query)

        # Wrap in str() to enforce string return type, avoiding "Returning Any" errors
        return str(render_template("search.html", books=books, query=query))

    except Exception as e:
        logger.error(f"Failed to search: {e}", exc_info=True)
        error_message = f"Search Failed: {str(e)}"
        # Wrap in str() to enforce string return type
        return str(render_template("search.html", books=books, error=error_message, query=query))


@main_bp.route("/details")
@limiter.limit("30 per minute")
def details() -> str | Response:
    """Fetch and render the details page internally via the server."""
    link = request.args.get("link")
    if not link:
        # Cast redirect to Response to satisfy MyPy return type checking
        return cast(Response, redirect(url_for("main.search")))

    try:
        book_details = get_book_details(link)
        return str(render_template("details.html", book=book_details))
    except Exception as e:
        logger.error(f"Failed to fetch details: {e}", exc_info=True)
        return str(render_template("details.html", error=f"Could not load details: {str(e)}"))


# FIX: Updated return type to include tuple[Response, int] for error codes
@main_bp.route("/send", methods=["POST"])
@limiter.limit("60 per minute")
def send() -> Response | tuple[Response, int]:
    """API endpoint to initiate a download."""
    data = request.json

    if not isinstance(data, dict):
        logger.warning("Invalid send request: JSON body is not a dictionary.")
        return jsonify({"message": "Invalid JSON format"}), 400

    details_url = data.get("link") if data else None
    title = data.get("title") if data else None

    if not details_url or not title:
        logger.warning("Invalid send request received: missing link or title")
        return jsonify({"message": "Invalid request"}), 400

    # Sanitize title immediately for safe logging
    safe_title = sanitize_title(title)
    logger.info(f"Received download request for '{safe_title}'")

    try:
        magnet_link, error = extract_magnet_link(details_url)

        if not magnet_link:
            logger.error(f"Failed to extract magnet link for '{safe_title}': {error}")
            return jsonify({"message": f"Download failed: {error}"}), 500

        if safe_title == FALLBACK_TITLE:
            logger.warning(
                f"Title '{title}' was sanitized to fallback '{FALLBACK_TITLE}'. Files will be saved in a generic folder."
            )

        save_path_base = current_app.config.get("SAVE_PATH_BASE")
        if save_path_base:
            save_path = os.path.join(save_path_base, safe_title)
        else:
            save_path = safe_title

        torrent_manager.add_magnet(magnet_link, save_path)

        logger.info(f"Successfully sent '{safe_title}' to {torrent_manager.client_type}")
        return cast(
            Response,
            jsonify(
                {
                    "message": "Download added successfully! This may take some time; the download will show in Audiobookshelf when completed."
                }
            ),
        )
    except Exception as e:
        logger.error(f"Send failed: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


@main_bp.route("/delete", methods=["POST"])
def delete_torrent() -> Response | tuple[Response, int]:
    """API endpoint to remove a torrent."""
    data = request.json

    if not isinstance(data, dict):
        return jsonify({"message": "Invalid JSON format"}), 400

    torrent_id = data.get("id") if data else None

    if not torrent_id:
        return jsonify({"message": "Torrent ID is required"}), 400

    try:
        torrent_manager.remove_torrent(torrent_id)
        return cast(Response, jsonify({"message": "Torrent removed successfully."}))
    except Exception as e:
        logger.error(f"Failed to remove torrent: {e}", exc_info=True)
        return jsonify({"message": f"Failed to remove torrent: {str(e)}"}), 500


@main_bp.route("/reload_library", methods=["POST"])
def reload_library() -> Response | tuple[Response, int]:
    """API endpoint to trigger an Audiobookshelf library scan."""
    abs_url = current_app.config.get("ABS_URL")
    abs_key = current_app.config.get("ABS_KEY")
    abs_lib = current_app.config.get("ABS_LIB")

    if not all([abs_url, abs_key, abs_lib]):
        return jsonify({"message": "Audiobookshelf integration not configured."}), 400

    try:
        url = f"{abs_url}/api/libraries/{abs_lib}/scan"
        headers = {"Authorization": f"Bearer {abs_key}"}
        response = requests.post(url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("Audiobookshelf library scan initiated successfully.")
        return cast(Response, jsonify({"message": "Audiobookshelf library scan initiated."}))
    except requests.exceptions.RequestException as e:
        error_message = str(e)
        if e.response is not None:
            error_message = f"{e.response.status_code} {e.response.reason}: {e.response.text}"
        logger.error(f"ABS Scan Failed: {error_message}", exc_info=True)
        return jsonify({"message": f"Failed to trigger library scan: {error_message}"}), 500


@main_bp.route("/status")
def status() -> str | Response | tuple[Response, int]:
    """Render the current status of downloads.

    Supports returning JSON for frontend polling via ?json=1.
    """
    try:
        torrent_list = torrent_manager.get_status()

        # FIX: Return JSON if requested by the frontend poller
        if request.args.get("json"):
            return cast(Response, jsonify(torrent_list))

        logger.debug(f"Retrieved status for {len(torrent_list)} torrents.")
        # Wrap in str() to ensure return type is string
        return str(render_template("status.html", torrents=torrent_list))
    except Exception as e:
        logger.error(f"Failed to fetch torrent status: {e}", exc_info=True)

        # FIX: Return JSON error if polling, otherwise render error page
        if request.args.get("json"):
            return jsonify({"error": str(e)}), 500

        # Wrap in str() to ensure return type is string
        return str(render_template("status.html", torrents=[], error=f"Error connecting to client: {str(e)}"))
