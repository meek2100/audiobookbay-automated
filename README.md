<!-- File: README.md -->

# AudiobookBay Automated

AudiobookBay Automated is a lightweight web application designed to simplify audiobook management. It allows users to
search [**AudioBook Bay**](https://audiobookbay.lu/) for audiobooks and send magnet links directly to a designated
**Deluge, qBittorrent, Transmission, or Put.io** client.

## How It Works

- **Search Results**: Users search for audiobooks. The app grabs results from AudioBook Bay and displays results with
  the **title** and **cover image**, along with two action links:
  1. **More Details**: Opens the audiobook's page on AudioBook Bay for additional information.
  2. **Download**: Sends the audiobook to your configured torrent client for downloading.

- **Magnet Link Generation**: When a user selects "Download," the app generates a magnet link from the infohash
  displayed on AudioBook Bay and sends it to the torrent client. Along with the magnet link, the app assigns:
  - A **category label** for organizational purposes.
  - A **save location** for downloaded files.

> **Note**: This app does not download or move any material itself (including torrent files). It only searches AudioBook
> Bay and facilitates magnet link generation for the torrent client.

## Features

- **Search Audiobook Bay**: Easily search for audiobooks by title or keywords.
- **Private Details View**: Browse book descriptions, file sizes, and tracker info internally. The app acts as a proxy,
  ensuring your IP address is never exposed to AudiobookBay while browsing.
- **Basic Download Status Page**: Monitor the download status of items in your torrent client that share the specified
  category assigned.
- **No AudioBook Bay Account Needed**: The app automatically generates magnet links from the displayed infohashes and
  pushes them to your torrent client for downloading.
- **Automatic Folder Organization**: Once the download is complete, the torrent client will automatically move the
  downloaded audiobook files to your save location. Audiobooks are organized into subfolders named after the AudioBook
  Bay title, making it easy for [**Audiobookshelf**](https://www.audiobookshelf.org/) to automatically add completed
  downloads to its library.
- **Audiobookshelf Integration**: (Optional) Automatically trigger a library scan in Audiobookshelf via a button in the
  UI.

## Why Use This?

AudiobookBay Automated provides a simple and user-friendly interface for users to download audiobooks without searching
on their own and import them into your library.

---

## Installation

### Prerequisites

- **Deluge, qBittorrent, Transmission, or Put.io** (with WebUI or API access)
- **Docker** (optional, for containerized deployments)
- **Python 3.13 - 3.14** (for local execution)

> **Important for Deluge Users**: It is **strongly recommended** to enable the **Label** plugin in your Deluge client
> (WebUI or GTK). This app uses the plugin to categorize downloads. If the plugin is missing or disabled, the app will
> still function and add downloads, but they will **not be categorized**, and the "Status" page may not be able to track
> them effectively. Transmission and qBittorrent support categorization natively without plugins.

### Environment Variables

The app uses environment variables to configure its behavior.

### Environment Variables

Setting up AudiobookBay Automated only takes a few minutes. To keep things as simple as possible, the settings below are
organized into three tiers:

1. **Standard Setup (Required)** — The only variables most users ever need to set.
2. **Optional & Customization** — Useful features like theme colors or connecting to Audiobookshelf.
3. **Advanced & Developer Only** — Fine-tuning, network overrides, and troubleshooting tools (most users can leave these
   alone).

---

#### 1. Standard Setup (Required)

These settings connect the app to your torrent client and define where audiobooks should be downloaded.

```env
# --- Download Client Connection ---
DL_CLIENT=qbittorrent          # Your client: qbittorrent, transmission, deluge, or putio
DL_HOST=192.168.1.123          # IP address or hostname of your client (not needed for putio)
DL_PORT=8080                   # WebUI port of your client (e.g. 8080 for qBittorrent, 9091 for Transmission)
DL_USERNAME=admin              # WebUI username
DL_PASSWORD=password           # WebUI password (or your Put.io token)

# --- Save Location & Security ---
SAVE_PATH_BASE=/audiobooks     # IMPORTANT: The path where files are stored inside your torrent client
SECRET_KEY=change_me           # Any long, random secret text to secure browser sessions
```

> [!TIP] **Understanding `SAVE_PATH_BASE`:** This is the folder path **as seen by your torrent client**, not this app.
> For example, if your qBittorrent container maps `/media/audiobooks` to `/downloads`, set this to `/downloads`.

---

#### 2. Optional & Customization Settings

Everything below works out-of-the-box with sensible defaults, but you can customize them if you'd like.

```env
# --- Appearance & Theme ---
DEFAULT_THEME=purple           # Color theme: purple (default), dark, light, or crow
SITE_TITLE=AudiobookBay Automated # Name shown in the header and browser tab
SPLASH_ENABLED=True            # Show the welcome intro video on first visit (True or False)

# --- Audiobookshelf Integration ---
# Enables the "Reload Library" button in the navigation drawer to immediately scan for new books
ABS_URL=http://192.168.1.123:13378 # URL to your Audiobookshelf server
ABS_KEY=your_api_token             # Found in Audiobookshelf: Settings -> Users -> API Token
ABS_LIB=your_library_id            # Library ID from your browser address bar when viewing the library

# --- Custom Navigation Link ---
# Adds a quick-link button to your navigation menu (e.g., to open your player)
NAV_LINK_NAME=Open Player
NAV_LINK_URL=http://192.168.1.123:13378
```

---

#### 3. Advanced & Developer Settings

> [!NOTE] You do **not** need to touch these settings for normal day-to-day use. They are provided for specialized
> network setups, debugging, or custom container configurations.

```env
# --- Network & Server Binding ---
LISTEN_PORT=5078               # Internal port the app listens on (Default: 5078)
LISTEN_HOST=0.0.0.0            # Network interface to bind to (Default: 0.0.0.0)
DL_SCHEME=http                 # Protocol for torrent client: http or https (Default: http)
DL_CATEGORY=abb-automated      # Category label applied to torrents (Default: abb-automated)

# --- Scraping & Mirror Overrides ---
ABB_HOSTNAME=audiobookbay.lu   # Primary search mirror (Default: audiobookbay.lu)
ABB_MIRRORS=audiobookbay.is,audiobookbay.se # Backup mirrors tried automatically if primary is down
PAGE_LIMIT=3                   # Number of search pages to scrape per query (Default: 3)
MAGNET_TRACKERS=udp://...      # Extra public trackers to append to generated magnet links

# --- Logging & Troubleshooting (Developers) ---
LOG_LEVEL=INFO                 # Verbosity: DEBUG, INFO, WARNING, ERROR (Default: INFO)
ENABLE_DIAGNOSTICS=false       # Enables the /diagnostics live health dashboard and scraper inspector
```

### Using Docker

1. Use `docker-compose` for quick deployment. You can find ready-to-use templates in the [`examples/`](examples/)
   directory.
   - **Recommended:** [`examples/docker-compose.env.yaml`](examples/docker-compose.env.yaml) (Uses a `.env` file for
     security)
   - **Alternative:** [`examples/docker-compose.no-env.yaml`](examples/docker-compose.no-env.yaml) (Hardcoded
     configuration)

   Download the example file to your server (e.g., using `wget` or `curl`) and rename it to `docker-compose.yml`.

2. **Start the Application**:

   ```bash
   docker-compose up -d
   ```

### Running Locally

1. **Install Dependencies**: Ensure you have **Python 3.13+** installed (3.14 recommended), then install the required
   dependencies:

   ```bash
   # Install from pyproject.toml
   pip install .
   ```

2. **Configure Environment**: Copy the example environment file to `.env`:

   ```bash
   cp examples/.env.example .env
   ```

### Advanced: Custom Trackers

If you wish to supply a long list of trackers that exceeds environment variable limits, you can mount a JSON file to
`/app/trackers.json` inside the container.

1. Create a `trackers.json` file. See [`examples/trackers.json`](examples/trackers.json) for the required format.
2. Update your `docker-compose.yaml` to include the volume mount:

```yaml
volumes:
  - ./trackers.json:/app/trackers.json:ro
```

The application will automatically detect this file and prioritize it over the default tracker list.

---

## Notes

- **This app does NOT download any material**: It simply generates magnet links and sends them to your configured
  torrent client for handling.

- **Folder Mapping**: **The `SAVE_PATH_BASE` is based on the perspective of your torrent client**, not this app. This
  app does not move any files; all file handling and organization are managed by the torrent client. Ensure that the
  `SAVE_PATH_BASE` in your torrent client aligns with your audiobook library (e.g., for Audiobookshelf). Using a path
  relative to where this app is running, instead of the torrent client, will cause issues.

---

## Feedback and Contributions

This project is production-ready, but your feedback is always welcome! Feel free to open issues or contribute by
submitting pull requests.

**Developers:** Please review [`AGENTS.md`](AGENTS.md) for strict architectural rules and coding standards before
contributing.

---

## Screenshots

### Search Page

![Search Interface showing results with filtering options](docs/images/search.png)

### Details Page

![Book details page showing description and trackers](docs/images/details.png)

### Status Page

![Download status page showing active torrents](docs/images/status.png)

---
