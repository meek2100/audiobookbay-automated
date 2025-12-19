# File: audiobook_automated/routes.py
"""Routes module handling all web endpoints."""

import logging
import os
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, cast

import requests
from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, url_for

from audiobook_automated.constants import (
    ABS_TIMEOUT_SECONDS,
    DEEP_PATH_WARNING_THRESHOLD,
    DEFAULT_COVER_FILENAME,
    MAX_FILENAME_LENGTH,
    MIN_FILENAME_LENGTH,
    MIN_SEARCH_QUERY_LENGTH,
    WINDOWS_PATH_SAFE_LIMIT,
)

from .extensions import limiter, torrent_manager
from .scraper import extract_magnet_link, get_book_details, search_audiobookbay
from .scraper.parser import BookSummary
from .utils import ensure_collision_safety, sanitize_title

logger = logging.getLogger(__name__)

# Create the Blueprint
main_bp = Blueprint("main", __name__)


@main_bp.context_processor
def inject_global_vars() -> dict[str, Any]:
    """Inject global variables into all templates.

    Uses current_app.config to access settings loaded in config.py.

    Returns:
        dict[str, Any]: A dictionary of context variables available to templates.
    """
    # Retrieve the pre-calculated hash from config to avoid disk I/O on every request.
    static_version = current_app.config.get("STATIC_VERSION", "v1")

    # OPTIMIZATION: Retrieve pre-calculated flag from config instead of re-evaluating
    # Now uses the property defined in Config class
    library_reload_enabled = current_app.config.get("LIBRARY_RELOAD_ENABLED", False)

    return {
        "nav_link_name": current_app.config.get("NAV_LINK_NAME"),
        "nav_link_url": current_app.config.get("NAV_LINK_URL"),
        "library_reload_enabled": library_reload_enabled,
        "static_version": static_version,
        "default_cover_filename": DEFAULT_COVER_FILENAME,
    }


@main_bp.route("/health")
def health() -> Response:
    """Perform a health check.

    Returns:
        Response: A JSON response with status "ok".
    """
    return jsonify({"status": "ok"})


@main_bp.route("/", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def search() -> str | Response:
    """Handle the search interface.

    Processes search queries and renders the search results page.
    Enforces a minimum query length of 2 characters.

    Query Params:
        query (str): The search term passed via GET or POST.

    Returns:
        str | Response: Rendered HTML template or Response object.
    """
    books: list[BookSummary] = []
    query = ""
    error_message = None

    try:
        query = request.args.get("query") or request.form.get("query") or ""
        query = query.strip()

        if query:
            # SAFETY: Minimum length check to prevent scraping spam
            if len(query) < MIN_SEARCH_QUERY_LENGTH:
                error_message = f"Search query must be at least {MIN_SEARCH_QUERY_LENGTH} characters long."
                return render_template("search.html", books=[], error=error_message, query=query)

            # AudiobookBay requires lowercase search terms
            search_query = query.lower()
            logger.info(f"Received search query: '{query}' (normalized to '{search_query}')")
            books = search_audiobookbay(search_query)

        return render_template("search.html", books=books, query=query)

    except ConnectionError as ce:
        # Specific handling for when mirrors are unreachable
        logger.error(f"Search failed due to connection error: {ce}")
        error_message = "Could not connect to AudiobookBay mirrors. Please try again later."
        return render_template("search.html", books=books, error=error_message, query=query)

    except Exception as e:
        logger.error(f"Failed to search: {e}", exc_info=True)
        error_message = f"Search Failed: {str(e)}"
        return render_template("search.html", books=books, error=error_message, query=query)


@main_bp.route("/details")
@limiter.limit("30 per minute")
def details() -> str | Response:
    """Fetch and render the details page internally via the server.

    Acts as a proxy to fetch book details from AudiobookBay without exposing the
    client's IP address to the external site.

    Query Params:
        link (str): The URL of the book details page.

    Returns:
        str | Response: Rendered HTML template or Redirect.
    """
    link = request.args.get("link")
    if not link:
        return cast(Response, redirect(url_for("main.search")))

    try:
        book_details = get_book_details(link)
        return render_template("details.html", book=book_details)
    except Exception as e:
        logger.error(f"Failed to fetch details: {e}", exc_info=True)
        return render_template("details.html", error=f"Could not load details: {str(e)}")


@main_bp.route("/send", methods=["POST"])
@limiter.limit("60 per minute")
def send() -> Response | tuple[Response, int]:
    """Initiate a download.

    Generates a magnet link and sends it to the configured torrent client.

    JSON Body:
        link (str): The details URL of the book.
        title (str): The title of the book.

    Returns:
        Response: JSON indicating success or failure.
    """
    data = request.json

    if not isinstance(data, dict):
        logger.warning("Invalid send request: JSON body is not a dictionary.")
        return jsonify({"message": "Invalid JSON format"}), 400

    details_url = data.get("link") if data else None
    title = data.get("title") if data else None

    # TYPE SAFETY: Ensure title is a string before calling string methods.
    if title is not None and not isinstance(title, str):
        logger.warning(f"Invalid send request: Title is not a string (Type: {type(title)}).")
        return jsonify({"message": "Invalid request: Title must be a string"}), 400

    # Check raw title existence. We must allow titles that sanitize to FALLBACK_TITLE (e.g. "...")
    # to proceed to the collision handler, rather than blocking them as "Invalid".
    if not details_url or not title or not title.strip():
        logger.warning("Invalid send request received: missing link or valid title")
        return jsonify({"message": "Invalid request: Title or Link missing"}), 400

    safe_title = sanitize_title(title)

    logger.info(f"Received download request for '{safe_title}'")

    try:
        magnet_link, error = extract_magnet_link(details_url)

        if not magnet_link:
            logger.error(f"Failed to extract magnet link for '{safe_title}': {error}")
            # Map specific errors to 404/400 to avoid alerting on 500s
            status_code = 404 if error and "found" in error else 400
            return jsonify({"message": f"Download failed: {error}"}), status_code

        # Dynamic Path Safety Calculation
        # Calculate available length for directory name based on SAVE_PATH_BASE length.
        # Max path on Windows is ~260. We reserve margin.
        save_path_base = current_app.config.get("SAVE_PATH_BASE")
        max_len = MAX_FILENAME_LENGTH  # Default safe default
        if save_path_base:
            base_len = len(save_path_base)
            # Use constant for calculation: 260 - 10 - 1 = 249
            calculated_limit = WINDOWS_PATH_SAFE_LIMIT - base_len

            if calculated_limit < DEEP_PATH_WARNING_THRESHOLD:
                logger.warning(
                    f"SAVE_PATH_BASE is extremely deep ({base_len} chars). "
                    "Titles will be severely truncated to prevent file system errors."
                )

            # SAFETY: Prioritize OS limits over "usable" length.
            # We enforce a floor of MIN_FILENAME_LENGTH to avoid empty strings/collisions,
            # but we cap the ceiling at the calculated limit to prevent crashes.
            max_len = max(MIN_FILENAME_LENGTH, calculated_limit)

            # Cap at MAX_FILENAME_LENGTH to ensure we never allow massive paths if base is short
            max_len = min(MAX_FILENAME_LENGTH, max_len)

        # Collision Prevention:
        # Handles Fallback Title, Windows Reserved names, and Path Length limits by appending UUID.
        previous_title = safe_title
        safe_title = ensure_collision_safety(safe_title, max_length=max_len)

        if safe_title != previous_title:
            msg = f"Title '{title}' required fallback/truncate handling. Using collision-safe directory name: {safe_title}"
            logger.warning(msg)

        if save_path_base:
            # NOTE: os.path.join uses the separator of the CONTAINER'S OS (Linux '/').
            # If the remote torrent client is on Windows (indicated by backslashes), we must construct
            # a Windows path even if running on Linux.
            if "\\" in save_path_base:
                save_path = str(PureWindowsPath(save_path_base).joinpath(safe_title))
            else:
                save_path = str(PurePosixPath(save_path_base).joinpath(safe_title))
        else:
            save_path = safe_title

        torrent_manager.add_magnet(magnet_link, save_path)

        logger.info(f"Successfully sent '{safe_title}' to {torrent_manager.client_type}")
        return (
            jsonify(
                {
                    "message": "Download added successfully! This may take some time; the download will show in Audiobookshelf when completed."
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"Send failed: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


@main_bp.route("/delete", methods=["POST"])
def delete_torrent() -> Response | tuple[Response, int]:
    """Remove a torrent.

    Requires a JSON payload with the torrent ID.

    JSON Payload:
        id (str): The ID or Hash of the torrent to remove.

    Returns:
        Response: JSON Response indicating success or failure.
    """
    data = request.json

    if not isinstance(data, dict):
        return jsonify({"message": "Invalid JSON format"}), 400

    torrent_id = data.get("id") if data else None

    if not torrent_id:
        return jsonify({"message": "Torrent ID is required"}), 400

    try:
        torrent_manager.remove_torrent(torrent_id)
        return jsonify({"message": "Torrent removed successfully."})
    except Exception as e:
        logger.error(f"Failed to remove torrent: {e}", exc_info=True)
        return jsonify({"message": f"Failed to remove torrent: {str(e)}"}), 500


@main_bp.route("/reload_library", methods=["POST"])
def reload_library() -> Response | tuple[Response, int]:
    """Trigger an Audiobookshelf library scan.

    Returns:
        Response: JSON indicating success or failure of the trigger request.
    """
    abs_url = current_app.config.get("ABS_URL")
    abs_key = current_app.config.get("ABS_KEY")
    abs_lib = current_app.config.get("ABS_LIB")

    if not all([abs_url, abs_key, abs_lib]):
        return jsonify({"message": "Audiobookshelf integration not configured."}), 400

    try:
        url = f"{abs_url}/api/libraries/{abs_lib}/scan"
        headers = {"Authorization": f"Bearer {abs_key}"}
        # TIMEOUT: Explicit timeout constant used to prevent hanging
        response = requests.post(url, headers=headers, timeout=ABS_TIMEOUT_SECONDS)
        response.raise_for_status()
        logger.info("Audiobookshelf library scan initiated successfully.")
        return jsonify({"message": "Audiobookshelf library scan initiated."})
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

    Query Params:
        json (str): If set to "1", "true", "yes", or "on", returns JSON instead of HTML.

    Returns:
        str | Response: Rendered HTML, JSON data, or Error Response.
    """
    # Robust boolean parsing
    json_arg = request.args.get("json", "").lower()
    is_json = json_arg in ("1", "true", "yes", "on")

    try:
        torrent_list = torrent_manager.get_status()

        if is_json:
            return jsonify(torrent_list)

        logger.debug(f"Retrieved status for {len(torrent_list)} torrents.")
        return render_template("status.html", torrents=torrent_list)
    except Exception as e:
        logger.error(f"Failed to fetch torrent status: {e}", exc_info=True)

        if is_json:
            return jsonify({"error": str(e)}), 500

        return render_template("status.html", torrents=[], error=f"Error connecting to client: {str(e)}")
