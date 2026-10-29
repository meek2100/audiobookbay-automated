<!-- File: docs/agents/torrent-clients.md -->

# Download Client Plugins & Extensibility Guide

## Download Client Plugin Interface

- All client implementations reside in `audiobook_automated/clients/` and inherit from `TorrentClientPlugin`.
- `TorrentManager` acts strictly as a facade and contains no client-specific code.
- Every client must implement `close()` to release sockets and sessions.
- Multi-client capability: `TorrentManager` manages multiple download clients configured via `DL_CLIENT` and
  `DL_CLIENTS`.

## Progress & Data Normalization

- Client plugins must normalize progress to a float between `0.0` and `100.0` rounded to 2 decimal places.
  - qBittorrent: API returns `0.0 - 1.0`; multiply by 100.
  - Transmission: API returns `0.0 - 100.0`; do not multiply by 100.
  - Deluge: API returns `0.0 - 100.0`; do not multiply by 100.
  - Put.io: API returns `0.0 - 100.0` (as `percent_done`); display `fetching meta..` when transfer size is 0.
- Reuse `format_size` from `audiobook_automated.utils`.

## Client-Specific Constraints

- qBittorrent: Leverage server-side filtering (`torrents_info(category=...)`). Support both string ("Ok.") and JSON API
  responses on add magnet. Supports API key authentication via `DL_API_KEY` or `DL_KEY`.
- Transmission: Filter torrents by label client-side in Python. Handle `http` vs `https` protocols explicitly. Inspect
  error strings on label failures to avoid masking system errors.
- Deluge: Detect presence of the "Label" plugin at connection. If absent, retrieve all torrents to maintain visibility.
  Handle missing plugin exceptions gracefully.
- Put.io: Cloud torrent client using REST API v2 (`DEFAULT_PORT = 443`). Authenticates via OAuth Bearer token
  (`DL_API_KEY`, `PUTIO_TOKEN`, or `DL_PASSWORD`). Supports custom target folder via `PUTIO_FOLDER_ID` (defaults to root
  `0`). Displays `fetching meta..` when transfer size is 0 during metadata resolution.

## Adding a New Download Client Plugin

1. Copy `audiobook_automated/clients/client_template.py` to create a new client plugin.
2. Implement required abstract methods adhering to normalization rules.
3. Define `DEFAULT_PORT` as a class attribute.
4. Auto-loaded by `TorrentManager` when `DL_CLIENT` matches the module filename.
