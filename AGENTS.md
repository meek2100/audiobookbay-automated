# Developer & AI Agent Guide

**READ THIS FIRST** before refactoring or "optimizing" this repository.

This project, `audiobookbay-automated`, is architected with a specific philosophy: **It is a single-user, self-hosted appliance.** It is NOT designed to be a scalable SaaS platform.

Optimizations that add complexity (e.g., Redis, Celery, complex databases) to support "scaling" are generally **anti-patterns** for this specific project unless they solve a critical failure in the single-user use case.

---

## 1. Core Architecture: The 'Single-User' Constraint

### The Concurrency Model (Critical)

- **Current Setup:** Gunicorn with `WORKERS=1` and `THREADS=8` (or more).
- **Why:** We use `Flask-Limiter` with in-memory storage (`memory://`).
  - _Constraint:_ In-memory limits are per-process. If you add multiple workers, you split the rate limit counters, effectively multiplying the allowed requests by the number of workers. This risks getting the user IP-banned by AudiobookBay.
  - _Instruction:_ **DO NOT** increase `WORKERS` above 1 without switching the rate limiter backend to Redis or a filesystem-based solution.
  - _Performance:_ Since the app is I/O bound (waiting on HTTP requests), Python threads are highly efficient. One worker with 8+ threads is sufficient for a single user.

### Global Request Semaphore (New)

- **Constraint:** Even with 1 worker/8 threads, a user could trigger 8 simultaneous scrapes (e.g., opening multiple tabs).
- **Solution:** `app.scraper.GLOBAL_REQUEST_SEMAPHORE` caps active HTTP requests to AudiobookBay at **2**.
- **Why:** This mimics a human user with 1-2 active tabs. It prevents the app from "hammering" the server, which triggers anti-bot protection. **Do not remove this semaphore.**

### The "Appliance" Philosophy

- **Statelessness:** The container should be as stateless as possible. It relies on the downstream Torrent Client (qBittorrent/Transmission) to manage state (downloads, file moves).
- **No Database:** We do not use an internal SQL database. We scrape on-demand and rely on the Torrent Client's API for status.
  - _Why:_ Keeps the Docker image small, startup fast, and maintenance zero.

### Privacy Proxying (Reader Mode)

- **Architecture:** The application acts as a privacy shield.
- **Requirement:** Features like "Book Details" MUST be rendered server-side (scraping via the container's VPN/IP) rather than linking the user directly to the source.
- **Why:** Prevents the user's residential/client IP from being exposed to the target website during browsing.

---

## 2. Robustness Over Raw Speed

### Rate Limiting & Scraping Strategy

- **Goal:** Mimic a human user to avoid anti-bot detection. Speed is secondary to avoiding IP bans.
- **Implementation:**
  - **Jitter:** Randomized sleeps (`time.sleep(1-3)`) are applied _before_ every scrape and magnet extraction. Do not remove these "for performance."
  - **Fail Fast (Mirrors):** Mirror availability checks (`check_mirror`) use `requests.head` directly with **zero retries**. We cycle through many mirrors quickly; waiting 90s for a retry loop on a dead mirror is bad UX.
  - **Input Normalization:** AudiobookBay search is case-sensitive and prefers lowercase. We normalize all search queries to lowercase in the controller (`app.py`) before scraping.

### Flask-Limiter Strategy (Opt-In)

- **Philosophy:** We use an **"Opt-In"** strategy, not "Opt-Out".
- **Rule:** Do NOT apply global default limits (e.g., `default_limits=["50 per hour"]`).
  - _Reason:_ Internal endpoints like `/health` (Docker heartbeat) and `/status` (auto-refresh) will trigger thousands of requests per day. Global limits will cause the container to go unhealthy.
- **Usage:** Apply `@limiter.limit` **only** to routes that hit external services (e.g., `/` search, `/send`, `/details`).

### Dependency Philosophy

- **Stability First:** We prefer robust, hardcoded lists over flaky dynamic dependencies.
  - _Example:_ We removed `fake_useragent` because its dynamic database fetching caused startup hangs. We now use a curated list of modern `USER_AGENTS` in `scraper.py`.

### Error Handling & Client Resilience

- **The "Eternal Spinner":** The frontend UI (`search.js`) must always assume the backend _might_ fail.
  - _Rule:_ All `fetch()` calls must have `.catch()` and `.finally()` blocks to reset UI states (loading spinners).
- **Downstream Failures:** The app must start even if the Torrent Client is offline.
  - _Implementation:_ Client instantiation in `clients.py` is wrapped in `try/except` to prevent boot crashes.
- **Deluge Specifics:** The `deluge-web-client` library can return `None` for result payloads when the daemon is unreachable (even if the WebUI is up). Code must explicitly check `if torrents.result:` before iterating.

---

## 3. Development Standards (Strict)

We enforce high code quality because "appliance" software is often difficult for end-users to debug.

### Security & SSRF Protection

- **Requirement:** Any endpoint accepting a URL for scraping (e.g., `/details`) MUST validate the domain.
- **Implementation:** Check `urlparse(link).netloc` against the `ABB_FALLBACK_HOSTNAMES` allowlist.
- **Why:** Prevents Server-Side Request Forgery (SSRF) where a malicious user could use the appliance to scan the internal network.

### Naming Conventions

- **Environment Variables:** Use standardized prefixes to avoid confusion.
  - `DL_*`: Downloader configurations (e.g., `DL_CLIENT`, `DL_HOST`, `DL_USERNAME`).
  - `ABS_*`: Audiobookshelf integrations (e.g., `ABS_URL`, `ABS_KEY`).
  - `ABB_*`: AudiobookBay configurations (e.g., `ABB_MIRRORS`).

### Python Versioning & Tooling

- **Runtime:** The Docker image runs **Python 3.13**.
- **Linting:** `pyproject.toml` is configured with `target-version = "py312"`.
  - _Reason:_ Some dev tools (like older Ruff versions or VS Code extensions) do not yet fully support 3.13 syntax. We stick to 3.12 syntax standards to ensure developer tooling compatibility while running on the latest runtime.

### Logging (Verbose)

- **Requirement:** Keep logging **VERBOSE** (Debug/Info).
- **Why:** In a self-hosted environment, we cannot see the user's network. "Noisy" logs (including connection details) are often the only way to debug DNS issues, ISP blocking, or rate limiting.
- **Configuration:** We explicitly configure the root logger to capture output from libraries like `urllib3` and `requests`. Do not silence them unless they emit gigabytes of useless binary data.

### Type Safety (Python 3.13+)

- **Requirement:** All Python code must be fully type-hinted.
- **Why:** We support Python 3.13+. Type hints act as self-documentation and catch bugs (like `None` handling) before runtime.
- **Tooling:** Pylance/MyPy compliant.

### Test Coverage (100%)

- **Requirement:** The test suite must maintain **100% code coverage**. This is enforced via `pytest --cov-fail-under=100`.
- **Security Testing:** You MUST include tests that explicitly enable CSRF protection (`WTF_CSRF_ENABLED = True`) to verify security headers work, even if standard tests disable it for convenience.
- **Unhappy Paths:** You must test failure modes (e.g., "what if the torrent client is offline?", "what if the website returns 500?", "what if metadata is missing?").
- **Valid Exemptions:** Use `# pragma: no cover` **only** for:
  - `if __name__ == "__main__":` blocks.
  - OS-specific logic (e.g., Windows-specific path handling if CI is Linux).
  - Gunicorn configuration blocks that cannot run in a test harness.

### Testing Style Guide

- **Framework:** Use **Pytest** exclusively. Do NOT use `unittest.TestCase` classes.
- **Fixtures:** Use `conftest.py` fixtures for setup/teardown (e.g., `client`, `mock_env`).
- **Mocking:**
  - Patch objects where they are **imported**, not where they are defined.
  - **Mock Network Calls:** Always mock `requests.get` and `requests.head`.
  - **Mock Sleep:** Always mock `time.sleep` to keep tests fast while verifying Jitter logic.
  - For startup logic (top-level code), use `importlib.reload(sys.modules["app.module"])` inside the test.

### Documentation

- **Docstrings:** All public functions and classes must have docstrings defining `Args` and `Returns`.
- **Comments:** Explain _why_ complex logic exists (e.g., regex fragility), not just _what_ it does.

---

## 4. Frontend & UX Philosophy

- **Navigation State (GET vs POST):** Search forms MUST use `GET` requests. This allows the browser's "Back" button to restore the previous search results and scroll position from the cache.
- **Notifications:** Prefer non-blocking "Toast" notifications (via `showNotification` in `actions.js`) over browser `alert()`.
- **External Link Warnings:** Any action that opens a link outside the application (e.g., "Open Original Page") MUST display a confirmation dialog warning the user that traffic will not be routed through the server/VPN.
- **Loading States:** Every button that triggers a backend fetch must disable itself and show a loading state (spinner or text change) immediately to prevent double-submissions.

---

## 5. Deployment & CI/CD

### Docker Optimization

- **Multi-Stage/Layering:** We install dependencies _before_ copying the app code to maximize Docker layer caching.
- **Preloading:** Gunicorn uses `--preload` to fail fast on syntax errors and save RAM (Copy-on-Write).
- **Timezones:** We install `tzdata` and pass `TZ` env var so logs match the user's wall clock (vital for personal self-hosting).

### CI Pipeline

- **Dependabot:** Configured to look in `/` (root) for `pyproject.toml`.
- **Tests:** We focus on "unhappy path" integration tests (timeouts, malformed HTML) because the happy path is easy. The real value is ensuring the app doesn't crash when the internet is flaky.

---

## 6. Future Refactoring Checklist

If you are asked to improve this repo, ask yourself:

1.  **"Does this remove a sleep() call?"** -> If YES, reject it. It protects the user from IP bans.
2.  **"Does this add a global rate limit?"** -> If YES, check if it blocks the healthcheck or status page auto-refresh.
3.  **"Does this require an external service (like Redis)?"** -> If YES, reject it unless absolutely necessary.
4.  **"Does this assume 100 concurrent users?"** -> If YES, you are optimizing for the wrong target. Optimize for **1 user doing 100 things sequentially**, not 100 users doing 1 thing.

## 7. Quick Reference

- **Install:** `pip install .` (Not requirements.txt)
- **Run Dev:** `python app/app.py`
- **Run Prod:** `entrypoint.sh` (Gunicorn)
- **Test:** `pytest`
