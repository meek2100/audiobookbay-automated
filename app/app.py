import logging
import os
import sys
from datetime import timedelta
from typing import Any

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
if __name__ != "__main__":  # pragma: no cover
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
else:  # pragma: no cover
    LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
    logging.basicConfig(
        level=LOG_LEVEL, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

logger = app.logger

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(days=365)

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

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    headers_enabled=True,  # Explicitly enable headers for tests and clients
)

SAVE_PATH_BASE = os.getenv("SAVE_PATH_BASE")
if not SAVE_PATH_BASE:
    if not IS_TESTING:
        logger.critical("Configuration Error: SAVE_PATH_BASE is missing.")
        sys.exit(1)

AUDIOBOOKSHELF_URL = os.getenv("AUDIOBOOKSHELF_URL")
ABS_KEY = os.getenv("ABS_KEY")
ABS_LIB = os.getenv("ABS_LIB")

# Optimization: Load Nav configs once at startup
NAV_LINK_NAME = os.getenv("NAV_LINK_NAME")
NAV_LINK_URL = os.getenv("NAV_LINK_URL")
LIBRARY_RELOAD_ENABLED = all([AUDIOBOOKSHELF_URL, ABS_KEY, ABS_LIB])

torrent_manager = TorrentManager()

try:
    if not IS_TESTING:
        torrent_manager.verify_credentials()
except Exception as e:
    logger.error(f"STARTUP WARNING: Could not connect to torrent client. Details: {e}")


@app.context_processor
def inject_nav_link() -> dict[str, Any]:
    """Injects navigation links and capability flags into templates."""
    # Optimization: Use pre-loaded global variables
    return {
        "nav_link_name": NAV_LINK_NAME,
        "nav_link_url": NAV_LINK_URL,
        "library_reload_enabled": LIBRARY_RELOAD_ENABLED,
    }


@app.route("/health")
def health() -> Response:
    """Dedicated health check endpoint."""
    return jsonify({"status": "ok"})


<<<<<<< HEAD
=======
# Helper function to search AudiobookBay
def search_audiobookbay(query, max_pages=PAGE_LIMIT):
    """
    Searches AudiobookBay for a given query and scrapes the results.

    Args:
        query (str): The search term.
        max_pages (int): The maximum number of pages to scrape.

    Returns:
        list: A list of dictionaries, where each dictionary represents a book
              and contains its details.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    results = []

    print(f"Searching for '{query}' on https://{ABB_HOSTNAME}...")

    for page in range(1, max_pages + 1):
        url = f"https://{ABB_HOSTNAME}/page/{page}/?s={query.lower().replace(' ', '+')}"
        try:
            response = requests.get(url, headers=headers, timeout=15)
            # Raise an exception for bad status codes (4xx or 5xx)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to fetch page {page}. Reason: {e}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        posts = soup.select(".post")

        # If no posts are found on the page, stop paginating
        if not posts:
            print(f"No more results found on page {page}.")
            break

        print(f"Processing {len(posts)} posts on page {page}...")

        for post in posts:
            try:
                title_element = post.select_one(".postTitle > h2 > a")
                if not title_element:
                    continue  # Skip post if title is not found

                title = title_element.text.strip()
                link = f"https://{ABB_HOSTNAME}{title_element['href']}"

                # Check if the cover URL is valid, otherwise use the default
                cover_url = (
                    post.select_one("img")["src"] if post.select_one("img") else None
                )
                if cover_url and is_url_valid(cover_url):
                    cover = cover_url
                else:
                    cover = "/static/images/default_cover.jpg"

                post_info = post.select_one(".postInfo")
                post_info_text = (
                    post_info.get_text(separator=" ", strip=True) if post_info else ""
                )

                language_match = re.search(
                    r"Language:\s*(.*?)(?:\s*Keywords:|$)", post_info_text, re.DOTALL
                )
                language = language_match.group(1).strip() if language_match else "N/A"

                details_paragraph = post.select_one(
                    ".postContent p[style*='text-align:center']"
                )

                post_date, book_format, bitrate, file_size = "N/A", "N/A", "N/A", "N/A"

                if details_paragraph:
                    details_html = str(details_paragraph)

                    post_date_match = re.search(r"Posted:\s*([^<]+)", details_html)
                    post_date = (
                        post_date_match.group(1).strip() if post_date_match else "N/A"
                    )

                    format_match = re.search(
                        r"Format:\s*<span[^>]*>([^<]+)</span>", details_html
                    )
                    book_format = (
                        format_match.group(1).strip() if format_match else "N/A"
                    )

                    bitrate_match = re.search(
                        r"Bitrate:\s*<span[^>]*>([^<]+)</span>", details_html
                    )
                    bitrate = bitrate_match.group(1).strip() if bitrate_match else "N/A"

                    file_size_match = re.search(
                        r"File Size:\s*<span[^>]*>([^<]+)</span>\s*([^<]+)",
                        details_html,
                    )
                    if file_size_match:
                        file_size = f"{file_size_match.group(1).strip()} {file_size_match.group(2).strip()}"

                results.append(
                    {
                        "title": title,
                        "link": link,
                        "cover": cover,
                        "language": language,
                        "post_date": post_date,
                        "format": book_format,
                        "bitrate": bitrate,
                        "file_size": file_size,
                    }
                )
            except Exception as e:
                print(f"[ERROR] Could not process a post. Details: {e}")
                continue
    return results


# Helper function to extract magnet link from details page
def extract_magnet_link(details_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(details_url, headers=headers)
        if response.status_code != 200:
            print(
                f"[ERROR] Failed to fetch details page. Status Code: {response.status_code}"
            )
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract Info Hash
        info_hash_row = soup.find("td", string=re.compile(r"Info Hash", re.IGNORECASE))
        if not info_hash_row:
            print("[ERROR] Info Hash not found on the page.")
            return None
        info_hash = info_hash_row.find_next_sibling("td").text.strip()

        # Extract Trackers
        tracker_rows = soup.find_all(
            "td", string=re.compile(r"udp://|http://", re.IGNORECASE)
        )
        trackers = [row.text.strip() for row in tracker_rows]

        if not trackers:
            print("[WARNING] No trackers found on the page. Using default trackers.")
            trackers = [
                "udp://tracker.openbittorrent.com:80",
                "udp://opentor.org:2710",
                "udp://tracker.ccc.de:80",
                "udp://tracker.blackunicorn.xyz:6969",
                "udp://tracker.coppersurfer.tk:6969",
                "udp://tracker.leechers-paradise.org:6969",
            ]

        # Construct the magnet link
        trackers_query = "&".join(
            f"tr={requests.utils.quote(tracker)}" for tracker in trackers
        )
        magnet_link = f"magnet:?xt=urn:btih:{info_hash}&{trackers_query}"

        print(f"[DEBUG] Generated Magnet Link: {magnet_link}")
        return magnet_link

    except Exception as e:
        print(f"[ERROR] Failed to extract magnet link: {e}")
        return None


# Helper function to sanitize titles
def sanitize_title(title):
    return re.sub(r'[<>:"/\\|?*]', "", title).strip()


# Endpoint for search page
>>>>>>> main
@app.route("/", methods=["GET", "POST"])
def search() -> str:
    """Handles the search interface."""
    books: list[dict[str, Any]] = []
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
        error_message = f"Search Failed: {str(e)}"
        return render_template("search.html", books=books, error=error_message, query=query)


@app.route("/send", methods=["POST"])
@limiter.limit("60 per minute")
def send() -> Response:
    """API endpoint to initiate a download."""
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
    """API endpoint to remove a torrent."""
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
    """API endpoint to trigger an Audiobookshelf library scan."""
    if not LIBRARY_RELOAD_ENABLED:
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
    """Renders the current status of downloads."""
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
