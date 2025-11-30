import os
import logging
from flask import Flask, request, render_template, jsonify
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

# Import custom modules
from clients import TorrentManager
from scraper import search_audiobookbay, extract_magnet_link
from utils import sanitize_title

# Load environment variables
load_dotenv()

# Configure Logging
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Security Configuration
DEFAULT_SECRET = "change-this-to-a-secure-random-key"
SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET)

if SECRET_KEY == DEFAULT_SECRET:
    logger.warning("WARNING: You are using the default insecure SECRET_KEY. Please set a unique SECRET_KEY in your .env file for production!")

app.config['SECRET_KEY'] = SECRET_KEY
csrf = CSRFProtect(app)

# Initialize Managers
torrent_manager = TorrentManager()
SAVE_PATH_BASE = os.getenv("SAVE_PATH_BASE")

if not SAVE_PATH_BASE:
    logger.warning("STARTUP WARNING: SAVE_PATH_BASE is not set. Downloads may be saved to the torrent client's default location.")

@app.context_processor
def inject_nav_link():
    return {
        "nav_link_name": os.getenv("NAV_LINK_NAME"),
        "nav_link_url": os.getenv("NAV_LINK_URL"),
    }

@app.route("/", methods=["GET", "POST"])
def search():
    """
    Handles the search interface.

    GET: Renders the search page with an empty results table.
    POST: Accepts 'query' from the form, executes the scraper, and renders
          the search page populated with results.
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
        error_message = (
            "Unable to connect to AudiobookBay. This could be due to:\n"
            "1. AudiobookBay domains are temporarily down or blocked.\n"
            "2. Network connectivity issues.\n"
            "3. DNS resolution problems.\n\n"
            f"Technical Detail: {str(e)}"
        )
        return render_template(
            "search.html", books=books, error=error_message, query=query
        )

@app.route("/send", methods=["POST"])
def send():
    """
    API endpoint to initiate a download.

    Expects JSON payload: { "link": str, "title": str }

    Workflow:
    1. Extracts the magnet link from the provided AudiobookBay details URL.
    2. Sanitizes the title for filesystem safety.
    3. Adds the magnet link to the configured torrent client with the specific save path.
    """
    data = request.json
    details_url = data.get("link")
    title = data.get("title")

    if not details_url or not title:
        logger.warning("Invalid send request received: missing link or title")
        return jsonify({"message": "Invalid request"}), 400

    # Critical Check: Ensure SAVE_PATH_BASE is configured
    if not SAVE_PATH_BASE:
        logger.error("Configuration Error: SAVE_PATH_BASE is missing.")
        return jsonify({"message": "Server configuration error: SAVE_PATH_BASE is not set. Contact administrator."}), 500

    try:
        magnet_link = extract_magnet_link(details_url)
        if not magnet_link:
            return jsonify({"message": "Failed to extract magnet link"}), 500

        # Create save path using the utility function
        safe_title = sanitize_title(title)
        save_path = f"{SAVE_PATH_BASE}/{safe_title}"

        # Use the TorrentManager to handle the specific client logic
        torrent_manager.add_magnet(magnet_link, save_path)

        logger.info(f"Successfully sent '{title}' to {torrent_manager.client_type}")
        return jsonify({
            "message": "Download added successfully! This may take some time, the download will show in Audiobookshelf when completed."
        })
    except Exception as e:
        logger.error(f"Send failed: {e}")
        return jsonify({"message": str(e)}), 500

@app.route("/status")
def status():
    """
    Renders the current status of downloads.

    Fetches the list of active torrents from the configured client that match
    the application's category label and displays them in a table.
    """
    try:
        torrent_list = torrent_manager.get_status()
        return render_template("status.html", torrents=torrent_list)
    except Exception as e:
        logger.error(f"Failed to fetch torrent status: {e}")
        # Return the template with an error message instead of raw JSON
        return render_template("status.html", torrents=[], error=f"Error connecting to client: {str(e)}")

if __name__ == "__main__":
    # This block is used for local development only.
    # In Docker, Gunicorn is used via entrypoint.sh.
    host = os.getenv("LISTEN_HOST", "0.0.0.0")
    port = int(os.getenv("LISTEN_PORT", 5078))
    app.run(host=host, port=port)
