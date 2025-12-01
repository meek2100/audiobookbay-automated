import logging
import os
import sys
from datetime import timedelta

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

# Import custom modules
from .clients import TorrentManager
from .scraper import extract_magnet_link, search_audiobookbay
from .utils import sanitize_title

# Load environment variables
load_dotenv()

app = Flask(__name__)

# --- Logging Configuration ---
# OPTIMIZATION: Unify logging with Gunicorn if available
if __name__ != "__main__":  # pragma: no cover
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
else:
    LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
    logging.basicConfig(
        level=LOG_LEVEL, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

logger = app.logger

# OPTIMIZATION: Aggressive caching for static assets
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(days=365)

# Security Configuration
DEFAULT_SECRET = "change-this-to-a-secure-random-key"
SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET)

IS_DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
IS_TESTING = os.getenv("TESTING", "0") == "1"

if SECRET_KEY == DEFAULT_SECRET:
    if IS_DEBUG or IS_TESTING:
        logger.warning(
            "WARNING: You are using the default insecure SECRET_KEY. This is acceptable for development/testing but UNSAFE for production."
        )
    else:
        logger.critical("CRITICAL SECURITY ERROR: You are running in PRODUCTION with the default insecure SECRET_KEY.")
        raise ValueError("Application refused to start: Change SECRET_KEY in your .env file for production deployment.")

app.config["SECRET_KEY"] = SECRET_KEY
csrf = CSRFProtect(app)

# Rate Limiter Setup
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# --- Startup Checks ---
SAVE_PATH_BASE = os.getenv("SAVE_PATH_BASE")
if not SAVE_PATH_BASE:
    if not IS_TESTING:
        logger.critical("Configuration Error: SAVE_PATH_BASE is missing.")
        sys.exit(1)

# --- Audiobookshelf Integration Config ---
AUDIOBOOKSHELF_URL = os.getenv("AUDIOBOOKSHELF_URL")
ABS_KEY = os.getenv("ABS_KEY")
ABS_LIB = os.getenv("ABS_LIB")

# Initialize Manager
torrent_manager = TorrentManager()

# Verify connection
try:
    if not IS_TESTING:
        torrent_manager.verify_credentials()
except Exception as e:
    logger.error(f"STARTUP WARNING: Could not connect to torrent client. Details: {e}")


@app.context_processor
def inject_nav_link() -> dict:
    """Injects navigation links and capability flags into templates."""
    return {
        "nav_link_name": os.getenv("NAV_LINK_NAME"),
        "nav_link_url": os.getenv("NAV_LINK_URL"),
        "library_reload_enabled": all([AUDIOBOOKSHELF_URL, ABS_KEY, ABS_LIB]),
    }


@app.route("/health")
def health() -> Response:
    """
    Dedicated health check endpoint.
    Returns 200 OK without rendering templates or checking external services.
    """
    return jsonify({"status": "ok"})


@app.route("/", methods=["GET", "POST"])
def search() -> str:
    """
    Handles the search interface (GET to view, POST to submit).

    Returns:
        str: Rendered HTML template.
    """
    books = []
    query = ""
    error_message = None

    try:
        if request.method == "POST":
            query = request.form.get("query", "").strip()
            if query:
                books = search_audiobookbay(query)

        return render_template("search.html", books=books, query=query)

    except Exception as e:
        logger.error(f"Failed to search: {e}")
        # ROBUSTNESS: Display the specific error (e.g. Connection Error) to the user
        error_message = f"Search Failed: {str(e)}"
        # Pass variable name 'error' to match template expectation more cleanly
        return render_template("search.html", books=books, error=error_message, query=query)


@app.route("/send", methods=["POST"])
@limiter.limit("60 per minute")
def send() -> Response:
    """
    API endpoint to initiate a download.

    Returns:
        Response: JSON response with success/failure message.
    """
    data = request.json
    details_url = data.get("link") if data else None
    title = data.get("title") if data else None

    if not details_url or not title:
        logger.warning("Invalid send request received: missing link or title")
        return jsonify({"message": "Invalid request"}), 400

    try:
        magnet_link, error = extract_magnet_link(details_url)

        if not magnet_link:
            return jsonify({"message": f"Download failed: {error}"}), 500

        safe_title = sanitize_title(title)

        if SAVE_PATH_BASE:
            save_path = os.path.join(SAVE_PATH_BASE, safe_title)
        else:
            save_path = safe_title

        torrent_manager.add_magnet(magnet_link, save_path)

        logger.info(f"Successfully sent '{title}' to {torrent_manager.client_type}")
        return jsonify(
            {
                "message": "Download added successfully! This may take some time, the download will show in Audiobookshelf when completed."
            }
        )
    except Exception as e:
        logger.error(f"Send failed: {e}")
        return jsonify({"message": str(e)}), 500


@app.route("/delete", methods=["POST"])
def delete_torrent() -> Response:
    """
    API endpoint to remove a torrent.

    Returns:
        Response: JSON response indicating success or failure.
    """
    data = request.json
    torrent_id = data.get("id") if data else None

    if not torrent_id:
        return jsonify({"message": "Torrent ID is required"}), 400

    try:
        torrent_manager.remove_torrent(torrent_id)
        return jsonify({"message": "Torrent removed successfully."})
    except Exception as e:
        logger.error(f"Failed to remove torrent: {e}")
        return jsonify({"message": f"Failed to remove torrent: {str(e)}"}), 500


@app.route("/reload_library", methods=["POST"])
def reload_library() -> Response:
    """
    API endpoint to trigger an Audiobookshelf library scan.

    Returns:
        Response: JSON response from the ABS API or error message.
    """
    if not all([AUDIOBOOKSHELF_URL, ABS_KEY, ABS_LIB]):
        return jsonify({"message": "Audiobookshelf integration not configured."}), 400

    try:
        url = f"{AUDIOBOOKSHELF_URL}/api/libraries/{ABS_LIB}/scan"
        headers = {"Authorization": f"Bearer {ABS_KEY}"}
        response = requests.post(url, headers=headers, timeout=10)
        response.raise_for_status()
        return jsonify({"message": "Audiobookshelf library scan initiated."})
    except requests.exceptions.RequestException as e:
        error_message = str(e)
        if e.response is not None:
            error_message = f"{e.response.status_code} {e.response.reason}: {e.response.text}"
        logger.error(f"ABS Scan Failed: {error_message}")
        return jsonify({"message": f"Failed to trigger library scan: {error_message}"}), 500


@app.route("/status")
def status() -> str:
    """
    Renders the current status of downloads.

    Returns:
        str: Rendered HTML status page.
    """
    try:
        torrent_list = torrent_manager.get_status()
        return render_template("status.html", torrents=torrent_list)
    except Exception as e:
        logger.error(f"Failed to fetch torrent status: {e}")
        return render_template("status.html", torrents=[], error=f"Error connecting to client: {str(e)}")


if __name__ == "__main__":  # pragma: no cover
    host = os.getenv("LISTEN_HOST", "0.0.0.0")
    port = int(os.getenv("LISTEN_PORT", "5078"))
    app.run(host=host, port=port)
