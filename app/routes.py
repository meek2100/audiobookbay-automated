import logging
import os
from typing import Any

import requests
from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, url_for

# Import extensions and logic
from .extensions import limiter, torrent_manager
from .scraper import extract_magnet_link, get_book_details, search_audiobookbay
from .utils import calculate_static_hash, sanitize_title

logger = logging.getLogger(__name__)

# Create the Blueprint
main_bp = Blueprint("main", __name__)


@main_bp.context_processor
def inject_global_vars() -> dict[str, Any]:
    """
    Injects global variables into all templates.
    Uses current_app.config to access settings loaded in config.py.
    """
    # Calculate static hash on demand (or cached) could be optimized,
    # but for now we calculate once at module level or startup.
    # Note: Accessing app.root_path requires context, so we do it here or pass it in.
    static_folder = os.path.join(current_app.root_path, "static")
    static_version = calculate_static_hash(static_folder)

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
    }


@main_bp.route("/health")
def health() -> Response:
    """Dedicated health check endpoint."""
    return jsonify({"status": "ok"})


@main_bp.route("/", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def search() -> str:
    """Handles the search interface."""
    books: list[dict[str, Any]] = []
    query = ""
    error_message = None

    try:
        query = request.args.get("query") or request.form.get("query") or ""
        query = query.strip()

        if query:
            # OPTIMIZATION: AudiobookBay requires lowercase search terms
            search_query = query.lower()
            logger.info(f"Received search query: '{query}' (normalized to '{search_query}')")
            books = search_audiobookbay(search_query)

        return render_template("search.html", books=books, query=query)

    except Exception as e:
        logger.error(f"Failed to search: {e}", exc_info=True)
        error_message = f"Search Failed: {str(e)}"
        return render_template("search.html", books=books, error=error_message, query=query)


@main_bp.route("/details")
@limiter.limit("30 per minute")
def details() -> str | Response:
    """Fetches and renders the details page internally via the server."""
    link = request.args.get("link")
    if not link:
        return redirect(url_for("main.search"))

    try:
        book_details = get_book_details(link)
        return render_template("details.html", book=book_details)
    except Exception as e:
        logger.error(f"Failed to fetch details: {e}", exc_info=True)
        return render_template("details.html", error=f"Could not load details: {str(e)}")


@main_bp.route("/send", methods=["POST"])
@limiter.limit("60 per minute")
def send() -> Response:
    """API endpoint to initiate a download."""
    data = request.json
    details_url = data.get("link") if data else None
    title = data.get("title") if data else None

    if not details_url or not title:
        logger.warning("Invalid send request received: missing link or title")
        return jsonify({"message": "Invalid request"}), 400

    logger.info(f"Received download request for '{title}'")

    try:
        magnet_link, error = extract_magnet_link(details_url)

        if not magnet_link:
            logger.error(f"Failed to extract magnet link for '{title}': {error}")
            return jsonify({"message": f"Download failed: {error}"}), 500

        safe_title = sanitize_title(title)

        if safe_title == "Unknown_Title":
            logger.warning(
                f"Title '{title}' was sanitized to fallback 'Unknown_Title'. Files will be saved in a generic folder."
            )

        save_path_base = current_app.config.get("SAVE_PATH_BASE")
        if save_path_base:
            save_path = os.path.join(save_path_base, safe_title)
        else:
            save_path = safe_title

        torrent_manager.add_magnet(magnet_link, save_path)

        logger.info(f"Successfully sent '{title}' to {torrent_manager.client_type}")
        return jsonify(
            {
                "message": "Download added successfully! This may take some time; the download will show in Audiobookshelf when completed."
            }
        )
    except Exception as e:
        logger.error(f"Send failed: {e}", exc_info=True)
        return jsonify({"message": str(e)}), 500


@main_bp.route("/delete", methods=["POST"])
def delete_torrent() -> Response:
    """API endpoint to remove a torrent."""
    data = request.json
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
def reload_library() -> Response:
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
        return jsonify({"message": "Audiobookshelf library scan initiated."})
    except requests.exceptions.RequestException as e:
        error_message = str(e)
        if e.response is not None:
            error_message = f"{e.response.status_code} {e.response.reason}: {e.response.text}"
        logger.error(f"ABS Scan Failed: {error_message}", exc_info=True)
        return jsonify({"message": f"Failed to trigger library scan: {error_message}"}), 500


@main_bp.route("/status")
def status() -> str:
    """Renders the current status of downloads."""
    try:
        torrent_list = torrent_manager.get_status()
        logger.debug(f"Retrieved status for {len(torrent_list)} torrents.")
        return render_template("status.html", torrents=torrent_list)
    except Exception as e:
        logger.error(f"Failed to fetch torrent status: {e}", exc_info=True)
        return render_template("status.html", torrents=[], error=f"Error connecting to client: {str(e)}")
