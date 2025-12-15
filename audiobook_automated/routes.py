"""Routes module handling all web endpoints."""

import logging
import os
import uuid
from typing import Any, cast

import requests
from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, url_for

from audiobook_automated.constants import (
    ABS_TIMEOUT_SECONDS,
    DEFAULT_COVER_FILENAME,
    FALLBACK_TITLE,
    MIN_SEARCH_QUERY_LENGTH,
)

from .extensions import limiter, torrent_manager
from .scraper import extract_magnet_link, get_book_details, search_audiobookbay
from .scraper.parser import BookSummary
from .utils import sanitize_title

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
    return cast(Response, jsonify({"status": "ok"}))


@main_bp.route("/", methods=["GET", "POST"])
@limiter.limit("30 per minute")  # type: ignore[untyped-decorator, unused-ignore]
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
@limiter.limit("30 per minute")  # type: ignore[untyped-decorator, unused-ignore]
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
@limiter.limit("60 per minute")  # type: ignore[untyped-decorator, unused-ignore]
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
        return cast(Response, jsonify({"message": "Invalid JSON format"})), 400

    details_url = data.get("link") if data else None
    title = data.get("title") if data else None

    # Check raw title existence. We must allow titles that sanitize to FALLBACK_TITLE (e.g. "...")
    # to proceed to the collision handler, rather than blocking them as "Invalid".
    if not details_url or not title or not title.strip():
        logger.warning("Invalid send request received: missing link or valid title")
        return cast(Response, jsonify({"message": "Invalid request: Title or Link missing"})), 400

    safe_title = sanitize_title(title)

    logger.info(f"Received download request for '{safe_title}'")

    try:
        magnet_link, error = extract_magnet_link(details_url)

        if not magnet_link:
            logger.error(f"Failed to extract magnet link for '{safe_title}': {error}")
            return cast(Response, jsonify({"message": f"Download failed: {error}"})), 500

        # Collision Prevention:
        # 1. Fallback Title (Sanitization completely emptied the string, e.g. "...")
        # 2. _Safe Suffix (Reserved Windows filename like "CON" -> "CON_Safe")
        # In both cases, we append a UUID to ensure multiple books don't merge into one folder.
        # This is a critical data integrity check.
        if safe_title == FALLBACK_TITLE or safe_title.endswith("_Safe"):
            logger.warning(f"Title '{title}' required fallback handling ('{safe_title}'). Appending UUID for safety.")
            unique_id = uuid.uuid4().hex[:8]
            # Truncate title to ~240 chars to leave room for ID and ensure filesystem safety
            safe_title = f"{safe_title[:240]}_{unique_id}"
            logger.info(f"Using collision-safe directory name: {safe_title}")

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
    except ConnectionError as ce:
        # Upstream service unavailable (mirrors down)
        logger.error(f"Upstream connection failed during send: {ce}")
        return cast(
            Response,
            jsonify({"message": "Upstream service unavailable. Please try again later."}),
        ), 503
    except Exception as e:
        logger.error(f"Send failed: {e}", exc_info=True)
        return cast(Response, jsonify({"message": str(e)})), 500


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
        return cast(Response, jsonify({"message": "Invalid JSON format"})), 400

    torrent_id = data.get("id") if data else None

    if not torrent_id:
        return cast(Response, jsonify({"message": "Torrent ID is required"})), 400

    try:
        torrent_manager.remove_torrent(torrent_id)
        return cast(Response, jsonify({"message": "Torrent removed successfully."}))
    except Exception as e:
        logger.error(f"Failed to remove torrent: {e}", exc_info=True)
        return cast(
            Response,
            jsonify({"message": f"Failed to remove torrent: {str(e)}"}),
        ), 500


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
        return cast(Response, jsonify({"message": "Audiobookshelf integration not configured."})), 400

    try:
        url = f"{abs_url}/api/libraries/{abs_lib}/scan"
        headers = {"Authorization": f"Bearer {abs_key}"}
        # TIMEOUT: Explicit timeout constant used to prevent hanging
        response = requests.post(url, headers=headers, timeout=ABS_TIMEOUT_SECONDS)
        response.raise_for_status()
        logger.info("Audiobookshelf library scan initiated successfully.")
        return cast(Response, jsonify({"message": "Audiobookshelf library scan initiated."}))
    except requests.exceptions.RequestException as e:
        error_message = str(e)
        if e.response is not None:
            error_message = f"{e.response.status_code} {e.response.reason}: {e.response.text}"
        logger.error(f"ABS Scan Failed: {error_message}", exc_info=True)
        return cast(Response, jsonify({"message": f"Failed to trigger library scan: {error_message}"})), 500


@main_bp.route("/status")
def status() -> str | Response | tuple[Response, int]:
    """Render the current status of downloads.

    Supports returning JSON for frontend polling via ?json=1.

    Query Params:
        json (str): If set, returns JSON instead of HTML.

    Returns:
        str | Response: Rendered HTML, JSON data, or Error Response.
    """
    is_json = request.args.get("json")

    try:
        torrent_list = torrent_manager.get_status()

        if is_json:
            return cast(Response, jsonify(torrent_list))

        logger.debug(f"Retrieved status for {len(torrent_list)} torrents.")
        return render_template("status.html", torrents=torrent_list)
    except Exception as e:
        logger.error(f"Failed to fetch torrent status: {e}", exc_info=True)

        if is_json:
            return cast(Response, jsonify({"error": str(e)})), 500

        return render_template("status.html", torrents=[], error=f"Error connecting to client: {str(e)}")
