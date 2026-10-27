<!-- File: docs/agents/architecture.md -->

# Architecture & Concurrency Standards

## Core Architecture: The Single-User Constraint
- Single-user, self-hosted appliance model: Not a scalable SaaS platform.
- Gunicorn Configuration: `WORKERS=1`, `THREADS=8+`.
- In-memory rate limits (`memory://`) apply per process; never add workers without an external limiter backend.
- No internal SQL database, persistent local caches, or server-side sessions.
- Container maintains no persistent application state; torrent client manages download and file state.

## Thread Safety & State Isolation
- Stateful objects must be thread-local or isolated.
- `requests.Session` and torrent client instances must never be shared across threads.
- Subclass `threading.local` for typed thread-local storage (e.g., `class ClientLocal(threading.local)`).
- Shared memory caches must be guarded by thread locks defined in the same module (`audiobook_automated/scraper/network.py`).

## Concurrency Safeguards
- Global Request Semaphore: Initialized at startup to match `SCRAPER_THREADS`.
- Must never be bypassed, removed, or modified to exceed configured concurrency.
- Background executors (e.g., `_mirror_executor`) must register `signal.SIGTERM` handlers for clean container shutdown.

## Extension & Initialization
- Global extensions (e.g., `ScraperExecutor`, `TorrentManager`) must use the Flask `init_app()` pattern.
- No import-time binding of configuration values.
- Configuration must use `pydantic-settings`.
