import logging
import os
import sys

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

# Import custom modules
from .clients import TorrentManager
from .scraper import extract_magnet_link, search_audiobookbay
from .utils import sanitize_title

# Load environment variables
load_dotenv()

# Configure Logging
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Security Configuration
DEFAULT_SECRET = "change-this-to-a-secure-random-key"
SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET)

# Determine execution mode
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
# Default remains "memory://" which requires a single-worker deployment (handled in entrypoint.sh).
LIMITER_STORAGE = os.getenv("LIMITER_STORAGE", "memory://")

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=LIMITER_STORAGE,
)

# --- Configuration & Startup Checks ---
SAVE_PATH_BASE = os.getenv("SAVE_PATH_BASE")
if not SAVE_PATH_BASE:
    if not IS_TESTING:
        logger.critical("Configuration Error: SAVE_PATH_BASE is missing. This is required for downloads.")
        sys.exit(1)

# Initialize Managers
torrent_manager = TorrentManager()

# Verify connection immediately (Skip during tests)
try:
    if not IS_TESTING:
        torrent_manager.verify_credentials()
except Exception as e:
    # If connection fails, we log it but do not crash.
    # The user might fix the torrent client connectivity later without restarting this container.
    logger.error(f"STARTUP WARNING: Could not connect to torrent client. Details: {e}")


@app.context_processor
def inject_nav_link():
    return {
        "nav_link_name": os.getenv("NAV_LINK_NAME"),
        "nav_link_url": os.getenv("NAV_LINK_URL"),
    }


@app.route("/", methods=["GET", "POST"])
def search():
    """Handles the search interface."""
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
        error_message = f"Unable to connect to AudiobookBay.\nTechnical Detail: {str(e)}"
        return render_template("search.html", books=books, error=error_message, query=query)


@app.route("/send", methods=["POST"])
@limiter.limit("10 per minute")  # Protect against spamming downloads
def send():
    """API endpoint to initiate a download."""
    data = request.json
    details_url = data.get("link")
    title = data.get("title")

    if not details_url or not title:
        logger.warning("Invalid send request received: missing link or title")
        return jsonify({"message": "Invalid request"}), 400

    try:
        # Unpack result and error
        magnet_link, error = extract_magnet_link(details_url)

        if not magnet_link:
            return jsonify({"message": f"Download failed: {error}"}), 500

        safe_title = sanitize_title(title)

        # Safer path construction
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


@app.route("/status")
def status():
    """Renders the current status of downloads."""
    try:
        torrent_list = torrent_manager.get_status()
        return render_template("status.html", torrents=torrent_list)
    except Exception as e:
        logger.error(f"Failed to fetch torrent status: {e}")
        return render_template("status.html", torrents=[], error=f"Error connecting to client: {str(e)}")


if __name__ == "__main__":
    host = os.getenv("LISTEN_HOST", "0.0.0.0")
    port = int(os.getenv("LISTEN_PORT", 5078))
    app.run(host=host, port=port)
