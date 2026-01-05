# File: audiobook_automated/routes.py
"""Routes module handling all web endpoints."""

import logging
from dataclasses import asdict
from typing import Any, cast

import requests
from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, url_for

from audiobook_automated.constants import (
    ABS_TIMEOUT_SECONDS,
    DEFAULT_COVER_FILENAME,
    ERROR_HASH_NOT_FOUND,
    MIN_SEARCH_QUERY_LENGTH,
)
from audiobook_automated.errors import AppError, InvalidRequestError, TorrentClientError

from .extensions import limiter, talisman, torrent_manager
from .scraper import extract_magnet_link, get_book_details, search_audiobookbay
from .scraper.parser import BookSummary
from .utils import construct_safe_save_path, parse_bool, sanitize_title

logger = logging.getLogger(__name__)

# Create the Blueprint
main_bp = Blueprint("main", __name__)


@main_bp.errorhandler(AppError)
def handle_app_error(error: AppError) -> tuple[Response, int]:
    """Handle custom application errors and return JSON response."""
    logger.error(f"AppError: {error.message}")
    return jsonify({"message": error.message}), error.status_code


@main_bp.context_processor
def inject_global_vars() -> dict[str, Any]:
    """Inject global variables into all templates.

    Uses current_app.config to access settings loaded in config.py.

    Returns:
        dict[str, Any]: A dictionary of context variables available to templates.
    """
    # Retrieve version hash from app config (calculated at startup)
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
        "splash_enabled": current_app.config.get("SPLASH_ENABLED", True),
        "splash_title": current_app.config.get("SPLASH_TITLE", ""),
        "splash_message": current_app.config.get("SPLASH_MESSAGE", ""),
        "splash_duration": current_app.config.get("SPLASH_DURATION", 4500),
    }


@main_bp.route("/health")
@talisman(force_https=False)  # type: ignore[untyped-decorator, unused-ignore]
def health() -> Response | tuple[Response, int]:
    """Perform a comprehensive health check.

    Checks:
    1. Application is running.
    2. Torrent client is reachable.

    Returns:
        Response: JSON with status details. 200 if OK, 503 if degraded.
    """
    if torrent_manager.verify_credentials():
        return jsonify({"status": "ok", "client": "connected"})

    return jsonify({"status": "degraded", "client": "disconnected"}), 503


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
        raise InvalidRequestError("Invalid JSON format")

    details_url = data.get("link") if data else None
    title = data.get("title") if data else None

    # TYPE SAFETY: Ensure link and title are strings before proceeding.
    if details_url is not None and not isinstance(details_url, str):
        logger.warning(f"Invalid send request: Link is not a string (Type: {type(details_url)}).")
        raise InvalidRequestError("Invalid request: Link must be a string")

    # VALIDATION: Ensure link starts with http:// or https://
    if details_url and not (details_url.startswith("http://") or details_url.startswith("https://")):
        logger.warning(f"Invalid send request: Link has invalid protocol ({details_url}).")
        raise InvalidRequestError("Invalid request: Link must start with http:// or https://")

    # TYPE SAFETY: Ensure title is a string before calling string methods.
    if title is not None and not isinstance(title, str):
        logger.warning(f"Invalid send request: Title is not a string (Type: {type(title)}).")
        raise InvalidRequestError("Invalid request: Title must be a string")

    # Check raw title existence. We must allow titles that sanitize to FALLBACK_TITLE (e.g. "...")
    # to proceed to the collision handler, rather than blocking them as "Invalid".
    if not details_url or not title or not title.strip():  # pragma: no cover
        logger.warning("Invalid send request received: missing link or valid title")
        raise InvalidRequestError("Invalid request: Title or Link missing")

    # Logging raw title before processing
    logger.info(f"Received download request for '{sanitize_title(title)}'")

    try:
        magnet_link, error = extract_magnet_link(details_url)

        if not magnet_link:
            logger.error(f"Failed to extract magnet link for '{title}': {error}")
            # Map specific errors to 404/400 to avoid alerting on 500s
            status_code = 404 if error == ERROR_HASH_NOT_FOUND else 400
            raise TorrentClientError(f"Download failed: {error}", status_code=status_code)

        # DELEGATION: Path construction logic moved to utils.py
        save_path_base = current_app.config.get("SAVE_PATH_BASE")
        save_path = construct_safe_save_path(save_path_base, title)

        torrent_manager.add_magnet(magnet_link, save_path)

        logger.info(f"Successfully sent '{title}' to {torrent_manager.client_type}")
        return (
            jsonify(
                {
                    "message": "Download added successfully! This may take some time; the download will show in Audiobookshelf when completed."
                }
            ),
            200,
        )
    except AppError:
        # Re-raise known app errors to be handled by the error handler
        raise
    except Exception as e:
        logger.error(f"Send failed: {e}", exc_info=True)
        raise TorrentClientError(str(e)) from e


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
        raise InvalidRequestError("Invalid JSON format")

    torrent_id = data.get("id") if data else None

    if not torrent_id:
        raise InvalidRequestError("Torrent ID is required")

    try:
        # Core Task 4: Verify category before deletion
        # Security: Prevent deleting torrents not managed by this application
        torrents = torrent_manager.get_status()
        target_torrent = next((t for t in torrents if t.id == torrent_id), None)

        if not target_torrent:
            return jsonify({"status": "error", "message": "Torrent not found"}), 404

        app_category = current_app.config.get("DL_CATEGORY", "abb-automated")
        # Robustness: Some clients (like Deluge) might not return category if label plugin missing
        # We check specific category match OR if the client doesn't support categories at all (fallback)
        if target_torrent.category and target_torrent.category != app_category:
            return jsonify(
                {
                    "status": "error",
                    "message": f"Security: Torrent category '{target_torrent.category}' does not match current app category '{app_category}'.",
                }
            ), 403

        torrent_manager.remove_torrent(torrent_id)
        return jsonify({"message": "Torrent removed successfully."})
    except Exception as e:
        logger.error(f"Failed to remove torrent: {e}", exc_info=True)
        raise TorrentClientError(f"Failed to remove torrent: {str(e)}") from e


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
    except requests.exceptions.HTTPError as e:
        # Pass upstream errors (4xx/5xx) directly to the user
        status_code = e.response.status_code if e.response is not None else 500
        error_message = f"{status_code} {e.response.reason}: {e.response.text}" if e.response is not None else str(e)
        logger.error(f"ABS Scan Failed (Upstream Error): {error_message}", exc_info=True)
        return jsonify({"message": f"Library scan failed: {error_message}"}), status_code
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
    is_json = parse_bool(request.args.get("json", ""))

    try:
        torrent_list = torrent_manager.get_status()

        if is_json:
            # Assumes torrent_manager.get_status returns Dataclasses as per architectural requirements.
            return jsonify([asdict(t) for t in torrent_list])

        logger.debug(f"Retrieved status for {len(torrent_list)} torrents.")
        return render_template("status.html", torrents=torrent_list)
    except Exception as e:
        logger.error(f"Failed to fetch torrent status: {e}", exc_info=True)

        if is_json:
            return jsonify({"error": str(e)}), 500

        return render_template("status.html", torrents=[], error=f"Error connecting to client: {str(e)}")
