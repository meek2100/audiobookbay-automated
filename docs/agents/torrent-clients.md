<!-- File: docs/agents/torrent-clients.md -->

# Torrent Client Strategy & Plugin Guide

## Client Strategy Interface
- All client implementations reside in `audiobook_automated/clients/` and inherit from `TorrentClientStrategy`.
- `TorrentManager` acts strictly as a facade and contains no client-specific code.
- Every strategy must implement `close()` to release sockets and sessions.

## Progress & Data Normalization
- Strategies must normalize progress to a float between `0.0` and `100.0` rounded to 2 decimal places.
  - qBittorrent: API returns `0.0 - 1.0`; multiply by 100.
  - Transmission: API returns `0.0 - 100.0`; do not multiply by 100.
  - Deluge: API returns `0.0 - 100.0`; do not multiply by 100.
- Re-use `format_size` from `audiobook_automated.utils`.

## Client-Specific Constraints
- qBittorrent: Leverage server-side filtering (`torrents_info(category=...)`). Support both string ("Ok.") and JSON API responses on add magnet.
- Transmission: Filter torrents by label client-side in Python. Handle `http` vs `https` protocols explicitly. Inspect error strings on label failures to avoid masking system errors.
- Deluge: Detect presence of the "Label" plugin at connection. If absent, retrieve all torrents to maintain visibility. Handle missing plugin exceptions gracefully.

## Plugin Extensibility
1. Copy `audiobook_automated/clients/client_template.py` to create new client strategies.
2. Implement required abstract methods adhering to normalization rules.
3. Define `DEFAULT_PORT` as a class attribute.
4. Auto-loaded by `TorrentManager` when `DL_CLIENT` matches the module filename.
