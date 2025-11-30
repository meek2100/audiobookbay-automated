import os
import re
import requests
import socket
import concurrent.futures
import logging
from cachetools import cached, TTLCache
from flask import Flask, request, render_template, jsonify
from bs4 import BeautifulSoup
from qbittorrentapi import Client
from transmission_rpc import Client as transmissionrpc
from deluge_web_client import DelugeWebClient as delugewebclient
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

# Configure Logging with Dynamic Levels
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration & Hostname Logic ---

# Sanitize the env var in case user included quotes (e.g. ABB_HOSTNAME="audiobookbay.is")
DEFAULT_HOSTNAME = os.getenv("ABB_HOSTNAME", "audiobookbay.lu").strip(" \"'")

# List of known AudiobookBay mirrors to try if the default fails
ABB_FALLBACK_HOSTNAMES = [
    DEFAULT_HOSTNAME,
    "audiobookbay.is",
    "audiobookbay.se",
    "audiobookbay.li",
    "audiobookbay.ws",
    "audiobookbay.la",
    "audiobookbay.me",
    "audiobookbay.fi",
    "theaudiobookbay.com",
    "audiobookbay.nl",
    "audiobookbay.pl"
]

# Deduplicate list while preserving order
ABB_FALLBACK_HOSTNAMES = list(dict.fromkeys(ABB_FALLBACK_HOSTNAMES))

PAGE_LIMIT = int(os.getenv("PAGE_LIMIT", 5))

DOWNLOAD_CLIENT = os.getenv("DOWNLOAD_CLIENT")
DL_URL = os.getenv("DL_URL")
if DL_URL:
    parsed_url = urlparse(DL_URL)
    DL_SCHEME = parsed_url.scheme
    DL_HOST = parsed_url.hostname
    DL_PORT = parsed_url.port
else:
    DL_SCHEME = os.getenv("DL_SCHEME", "http")
    DL_HOST = os.getenv("DL_HOST")
    DL_PORT = os.getenv("DL_PORT")

    # Make a DL_URL for Deluge if one was not specified
    if DL_HOST and DL_PORT:
        DL_URL = f"{DL_SCHEME}://{DL_HOST}:{DL_PORT}"

DL_USERNAME = os.getenv("DL_USERNAME")
DL_PASSWORD = os.getenv("DL_PASSWORD")
DL_CATEGORY = os.getenv("DL_CATEGORY", "Audiobookbay-Audiobooks")
SAVE_PATH_BASE = os.getenv("SAVE_PATH_BASE")

# Custom Nav Link Variables
NAV_LINK_NAME = os.getenv("NAV_LINK_NAME")
NAV_LINK_URL = os.getenv("NAV_LINK_URL")

# --- Intelligent Bind Address Logic ---
def get_smart_bind_address():
    """
    Determines the best bind address.
    1. If LISTEN_HOST env var is set, use it.
    2. Try binding to IPv6 '::' (often covers IPv4 too on dual-stack).
    3. Fallback to '0.0.0.0' (IPv4 only).
    """
    env_host = os.getenv("LISTEN_HOST")
    if env_host:
        return env_host

    try:
        # Attempt to create an IPv6 socket and bind to all interfaces
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.bind(('::', 0))
        s.close()
        logger.info("Auto-detected IPv6 support. Binding to '::' (Dual-Stack).")
        return '::'
    except Exception:
        logger.info("IPv6 bind failed. Falling back to '0.0.0.0' (IPv4).")
        return '0.0.0.0'

LISTEN_HOST = get_smart_bind_address()
LISTEN_PORT = int(os.getenv("LISTEN_PORT", 5078))

# Log configuration
logger.info(f"Starting app with Log Level: {LOG_LEVEL_STR}")
logger.info(f"Primary ABB_HOSTNAME: {DEFAULT_HOSTNAME}")
logger.info(f"Fallback Hostnames: {ABB_FALLBACK_HOSTNAMES}")
logger.info(f"DOWNLOAD_CLIENT: {DOWNLOAD_CLIENT}")
logger.info(f"DL_HOST: {DL_HOST}")
logger.info(f"DL_PORT: {DL_PORT}")
logger.info(f"DL_URL: {DL_URL}")
logger.info(f"DL_USERNAME: {DL_USERNAME}")
logger.info(f"DL_CATEGORY: {DL_CATEGORY}")
logger.info(f"SAVE_PATH_BASE: {SAVE_PATH_BASE}")
logger.info(f"NAV_LINK_NAME: {NAV_LINK_NAME}")
logger.info(f"NAV_LINK_URL: {NAV_LINK_URL}")
logger.info(f"PAGE_LIMIT: {PAGE_LIMIT}")
logger.info(f"LISTEN_HOST: {LISTEN_HOST}")
logger.info(f"LISTEN_PORT: {LISTEN_PORT}")


@app.context_processor
def inject_nav_link():
    return {
        "nav_link_name": os.getenv("NAV_LINK_NAME"),
        "nav_link_url": os.getenv("NAV_LINK_URL"),
    }

# --- Hostname Verification Logic ---

def check_mirror(hostname):
    """Checks if a specific hostname is reachable."""
    url = f"https://{hostname}/"
    try:
        # Use HEAD request for speed (don't download body)
        response = requests.head(url, timeout=5, allow_redirects=True)
        if response.status_code == 200:
            return hostname
    except Exception:
        pass
    return None

# Cache the working mirror for 10 minutes (600 seconds) to avoid re-checking every search
@cached(cache=TTLCache(maxsize=1, ttl=600))
def find_best_mirror():
    """
    Finds the fastest working AudiobookBay mirror.
    Checks all hostnames in parallel and returns the first one that responds.
    """
    logger.debug("Checking connectivity for all mirrors...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(ABB_FALLBACK_HOSTNAMES)) as executor:
        # Submit all checks at once
        future_to_host = {executor.submit(check_mirror, host): host for host in ABB_FALLBACK_HOSTNAMES}

        # As soon as one returns a result, use it
        for future in concurrent.futures.as_completed(future_to_host):
            result = future.result()
            if result:
                logger.info(f"Found active mirror: {result}")
                return result

    logger.error("No working AudiobookBay mirrors found!")
    return None


def fetch_and_parse_page(hostname, query, page):
    """
    Helper function to fetch and parse a single page of results.
    Accepts 'hostname' dynamically to support fallback logic.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    page_results = []
    # Construct URL using the verified hostname
    url = f"https://{hostname}/page/{page}/?s={query.replace(' ', '+')}"

    logger.debug(f"Fetching page {page} from {hostname}")

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        posts = soup.select(".post")

        if not posts:
            logger.debug(f"No posts found on page {page}")
            return []

        for post in posts:
            try:
                title_element = post.select_one(".postTitle > h2 > a")
                if not title_element:
                    continue

                title = title_element.text.strip()
                # Ensure the link points to the WORKING hostname, not the hardcoded one
                link = f"https://{hostname}{title_element['href']}"

                # Extract cover URL without validation (Client-side will handle errors)
                cover_url = (
                    post.select_one("img")["src"] if post.select_one("img") else None
                )
                cover = cover_url if cover_url else "/static/images/default_cover.jpg"

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

                page_results.append(
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
                # Log as error because parsing logic failing is an issue
                logger.error(f"Could not process a post on page {page}. Details: {e}")
                continue

    except requests.exceptions.RequestException as e:
        # Log as error because network failure impacts functionality
        logger.error(f"Failed to fetch page {page}. Reason: {e}")

    return page_results


# Helper function to search AudiobookBay with Caching and Parallelization
# Cache results for 1 hour (3600 seconds), max 32 items
@cached(cache=TTLCache(maxsize=32, ttl=3600))
def search_audiobookbay(query, max_pages=PAGE_LIMIT):
    """
    Searches AudiobookBay.
    1. Finds the best mirror (cached).
    2. Scrapes results in parallel using that mirror.
    """
    # Step 1: Get a working hostname
    active_hostname = find_best_mirror()

    if not active_hostname:
        raise Exception("Could not connect to any AudiobookBay mirrors.")

    logger.info(f"Searching for '{query}' on active mirror: https://{active_hostname}...")

    results = []

    # Step 2: Fetch pages in parallel using the active hostname
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_pages) as executor:
        # Create a dictionary to map futures to page numbers
        future_to_page = {
            executor.submit(fetch_and_parse_page, active_hostname, query, page): page
            for page in range(1, max_pages + 1)
        }

        for future in concurrent.futures.as_completed(future_to_page):
            try:
                page_data = future.result()
                results.extend(page_data)
            except Exception as exc:
                logger.error(f"Page generated an exception: {exc}")

    return results


# Helper function to extract magnet link from details page
def extract_magnet_link(details_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(details_url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Failed to fetch details page. Status Code: {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Extract Info Hash
        info_hash_row = soup.find("td", string=re.compile(r"Info Hash", re.IGNORECASE))
        if not info_hash_row:
            logger.error("Info Hash not found on the page.")
            return None
        info_hash = info_hash_row.find_next_sibling("td").text.strip()

        # Extract Trackers
        tracker_rows = soup.find_all(
            "td", string=re.compile(r"udp://|http://", re.IGNORECASE)
        )
        trackers = [row.text.strip() for row in tracker_rows]

        if not trackers:
            # WARN level: Unexpected but application can continue
            logger.warning("No trackers found on the page. Using default trackers.")
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

        # DEBUG level: Detailed info useful for troubleshooting but noisy
        logger.debug(f"Generated Magnet Link: {magnet_link}")
        return magnet_link

    except Exception as e:
        logger.error(f"Failed to extract magnet link: {e}")
        return None


# Helper function to sanitize titles
def sanitize_title(title):
    return re.sub(r'[<>:"/\\|?*]', "", title).strip()


# Endpoint for search page
@app.route("/", methods=["GET", "POST"])
def search():
    books = []
    query = ""
    error_message = None

    try:
        if request.method == "POST":
            query = request.form["query"]
            if query:  # Only search if the query is not empty
                books = search_audiobookbay(query)

                # If query is valid but no books found, check if it was a connection issue or just 0 results
                if not books:
                     # This check helps distinguish empty results from silent failures
                     pass

        return render_template("search.html", books=books, query=query)

    except Exception as e:
        logger.error(f"Failed to search: {e}")
        # User-friendly error message from PR suggestions
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


# Endpoint to send magnet link to qBittorrent
@app.route("/send", methods=["POST"])
def send():
    data = request.json
    details_url = data.get("link")
    title = data.get("title")
    if not details_url or not title:
        logger.warning("Invalid send request received: missing link or title")
        return jsonify({"message": "Invalid request"}), 400

    try:
        magnet_link = extract_magnet_link(details_url)
        if not magnet_link:
            return jsonify({"message": "Failed to extract magnet link"}), 500

        save_path = f"{SAVE_PATH_BASE}/{sanitize_title(title)}"

        if DOWNLOAD_CLIENT == "qbittorrent":
            qb = Client(
                host=DL_HOST, port=DL_PORT, username=DL_USERNAME, password=DL_PASSWORD
            )
            qb.auth_log_in()
            qb.torrents_add(urls=magnet_link, save_path=save_path, category=DL_CATEGORY)
        elif DOWNLOAD_CLIENT == "transmission":
            transmission = transmissionrpc(
                host=DL_HOST,
                port=DL_PORT,
                protocol=DL_SCHEME,
                username=DL_USERNAME,
                password=DL_PASSWORD,
            )
            transmission.add_torrent(magnet_link, download_dir=save_path)
        elif DOWNLOAD_CLIENT == "delugeweb":
            delugeweb = delugewebclient(url=DL_URL, password=DL_PASSWORD)
            delugeweb.login()
            delugeweb.add_torrent_magnet(
                magnet_link, save_directory=save_path, label=DL_CATEGORY
            )
        else:
            logger.error(f"Unsupported download client configured: {DOWNLOAD_CLIENT}")
            return jsonify({"message": "Unsupported download client"}), 400

        logger.info(f"Successfully sent '{title}' to {DOWNLOAD_CLIENT}")
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
    try:
        if DOWNLOAD_CLIENT == "transmission":
            transmission = transmissionrpc(
                host=DL_HOST, port=DL_PORT, username=DL_USERNAME, password=DL_PASSWORD
            )
            torrents = transmission.get_torrents()
            torrent_list = [
                {
                    "name": torrent.name,
                    "progress": round(torrent.progress, 2),
                    "state": torrent.status,
                    "size": f"{torrent.total_size / (1024 * 1024):.2f} MB",
                }
                for torrent in torrents
            ]
            return render_template("status.html", torrents=torrent_list)
        elif DOWNLOAD_CLIENT == "qbittorrent":
            qb = Client(
                host=DL_HOST, port=DL_PORT, username=DL_USERNAME, password=DL_PASSWORD
            )
            qb.auth_log_in()
            torrents = qb.torrents_info(category=DL_CATEGORY)
            torrent_list = [
                {
                    "name": torrent.name,
                    "progress": round(torrent.progress * 100, 2),
                    "state": torrent.state,
                    "size": f"{torrent.total_size / (1024 * 1024):.2f} MB",
                }
                for torrent in torrents
            ]
        elif DOWNLOAD_CLIENT == "delugeweb":
            delugeweb = delugewebclient(url=DL_URL, password=DL_PASSWORD)
            delugeweb.login()
            torrents = delugeweb.get_torrents_status(
                filter_dict={"label": DL_CATEGORY},
                keys=["name", "state", "progress", "total_size"],
            )
            torrent_list = [
                {
                    "name": torrent["name"],
                    "progress": round(torrent["progress"], 2),
                    "state": torrent["state"],
                    "size": f"{torrent['total_size'] / (1024 * 1024):.2f} MB",
                }
                for k, torrent in torrents.result.items()
            ]
        else:
            return jsonify({"message": "Unsupported download client"}), 400
        return render_template("status.html", torrents=torrent_list)
    except Exception as e:
        logger.error(f"Failed to fetch torrent status: {e}")
        return jsonify({"message": f"Failed to fetch torrent status: {e}"}), 500


if __name__ == "__main__":
    app.run(host=LISTEN_HOST, port=LISTEN_PORT)