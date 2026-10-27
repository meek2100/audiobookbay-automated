<!-- File: docs/agents/scraping-safety.md -->

# Scraping Safety & Filesystem Standards

## Safety Over Speed Invariants

- Mandatory Jitter: Introduce random sleep (0.5 to 1.5 seconds) prior to all external requests. Never remove or reduce.
- Network Calls: Never invoke `requests` directly; always route through `audiobook_automated/scraper/network.py`.
- Explicit Timeouts: Every blocking I/O operation must reference a named constant in `audiobook_automated/constants.py`.
- Search Query Limits: Search queries must meet minimum character length requirements (>= 2 characters) and normalize to
  lowercase.

## Mirror Probing & Negative Caching

- Mirror checks utilize `HEAD` requests without retries, falling back to `GET` on 403 or 405 status codes.
- Fail Fast: Probes must immediately return `None` on connection errors or timeouts.
- Negative Caching: If all external mirrors fail, cache the failure state for backoff (e.g., 30 seconds) to prevent
  retry storms. Do not purge mirror caches prematurely.

## Filesystem Safety & Path Boundaries

- Path Length Safety: Calculate maximum allowable directory length dynamically based on configured `SAVE_PATH_BASE` to
  honor OS path limits (such as 260 characters on Windows).
- Windows Reserved Names: Sanitize illegal characters and reserved words (e.g., `CON`, `PRN`, `AUX`, `NUL`), including
  compound extensions (e.g., `CON.tar.gz`).
- Collision Avoidance: Append short UUIDs (`uuid.uuid4().hex[:8]`) to sanitized or fallback directory names to guarantee
  uniqueness.
