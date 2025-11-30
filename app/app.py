import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFProtect

# Import custom modules
# [Modernization] Because we installed via pyproject.toml, standard relative imports work
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
APP_ENV = os.getenv("APP_ENV", "development").lower()

if SECRET_KEY == DEFAULT_SECRET:
    if APP_ENV == "production":
        logger.critical("CRITICAL SECURITY ERROR: You are running in PRODUCTION with the default insecure SECRET_KEY.")
        raise ValueError("Application refused to start: Change SECRET_KEY in your .env file for production deployment.")
    else:
        logger.warning(
            "WARNING: You are using the default insecure SECRET_KEY. Please set a unique SECRET_KEY in your .env file."
        )

app.config["SECRET_KEY"] = SECRET_KEY
csrf = CSRFProtect(app)

# Initialize Managers
torrent_manager = TorrentManager()
SAVE_PATH_BASE = os.getenv("SAVE_PATH_BASE")

if not SAVE_PATH_BASE:
    logger.warning(
        "STARTUP WARNING: SAVE_PATH_BASE is not set. Downloads may be saved to the torrent client's default location."
    )


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
        error_message = "Unable to connect to AudiobookBay.\n" f"Technical Detail: {str(e)}"
        return render_template("search.html", books=books, error=error_message, query=query)


@app.route("/send", methods=["POST"])
def send():
    """API endpoint to initiate a download."""
    data = request.json
    details_url = data.get("link")
    title = data.get("title")

    if not details_url or not title:
        logger.warning("Invalid send request received: missing link or title")
        return jsonify({"message": "Invalid request"}), 400

    if not SAVE_PATH_BASE:
        logger.error("Configuration Error: SAVE_PATH_BASE is missing.")
        return jsonify({"message": "Server configuration error: SAVE_PATH_BASE is not set."}), 500

    try:
        magnet_link = extract_magnet_link(details_url)
        if not magnet_link:
            return jsonify({"message": "Failed to extract magnet link"}), 500

        safe_title = sanitize_title(title)
        save_path = f"{SAVE_PATH_BASE}/{safe_title}"

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
