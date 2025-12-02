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

### The "Appliance" Philosophy

- **Statelessness:** The container should be as stateless as possible. It relies on the downstream Torrent Client (qBittorrent/Transmission) to manage state (downloads, file moves).
- **No Database:** We do not use an internal SQL database. We scrape on-demand and rely on the Torrent Client's API for status.
  - _Why:_ Keeps the Docker image small, startup fast, and maintenance zero.

---

## 2. Robustness Over Raw Speed

### Rate Limiting & Scraping

- **Goal:** Mimic a human user to avoid anti-bot detection.
- **Implementation:**
  - Randomized sleeps (`time.sleep(1-3)`) in `scraper.py`.
  - Relaxed rate limits (`60/min`) on sending downloads (user downloading a series).
  - Strict timeouts on HTTP requests to prevent "hanging" threads.
- **Agent Note:** Do not remove the `time.sleep` calls "for performance." They are a feature, not a bug.

### Error Handling

- **The "Eternal Spinner":** The frontend UI (`search.js`) must always assume the backend _might_ fail.
  - _Rule:_ All `fetch()` calls must have `.catch()` and `.finally()` blocks to reset UI states (loading spinners).
- **Downstream Failures:** The app must start even if the Torrent Client is offline.
  - _Implementation:_ Client instantiation in `clients.py` is wrapped in `try/except` to prevent boot crashes.

---

## 3. Development Standards (Strict)

We enforce high code quality because "appliance" software is often difficult for end-users to debug.

### Type Safety (Python 3.13+)

- **Requirement:** All Python code must be fully type-hinted.
- **Why:** We support Python 3.13+. Type hints act as self-documentation and catch bugs (like `None` handling) before runtime.
- **Tooling:** Pylance/MyPy compliant.

### Test Coverage (100%)

- **Requirement:** The test suite must maintain **100% code coverage**. This is enforced via `pytest --cov-fail-under=100`.
- **Unhappy Paths:** You must test failure modes (e.g., "what if the torrent client is offline?", "what if the website returns 500?"). The happy path is easy; the value is in ensuring resilience.
- **Valid Exemptions:** Use `# pragma: no cover` **only** for:
  - `if __name__ == "__main__":` blocks.
  - OS-specific logic (e.g., Windows-specific path handling if CI is Linux).
  - Gunicorn configuration blocks that cannot run in a test harness.

### Testing Style Guide

- **Framework:** Use **Pytest** exclusively. Do NOT use `unittest.TestCase` classes.
- **Fixtures:** Use `conftest.py` fixtures for setup/teardown (e.g., `client`, `mock_env`).
- **Mocking:**
  - Patch objects where they are **imported**, not where they are defined.
  - For startup logic (top-level code), use `importlib.reload(sys.modules["app.module"])` inside the test to re-run the initialization code.
  - For global state (like `limiter`), use an `autouse=True` fixture to reset state between tests.

### Documentation

- **Docstrings:** All public functions and classes must have docstrings defining `Args` and `Returns`.
- **Comments:** Explain _why_ complex logic exists (e.g., regex fragility), not just _what_ it does.

---

## 4. Deployment & CI/CD

### Docker Optimization

- **Multi-Stage/Layering:** We install dependencies _before_ copying the app code to maximize Docker layer caching.
- **Preloading:** Gunicorn uses `--preload` to fail fast on syntax errors and save RAM (Copy-on-Write).
- **Timezones:** We install `tzdata` and pass `TZ` env var so logs match the user's wall clock (vital for personal self-hosting).

### CI Pipeline

- **Dependabot:** Configured to look in `/` (root) for `pyproject.toml`.
- **Tests:** We focus on "unhappy path" integration tests (timeouts, malformed HTML) because the happy path is easy. The real value is ensuring the app doesn't crash when the internet is flaky.

---

## 5. Future Refactoring Checklist

If you are asked to improve this repo, ask yourself:

1.  **"Does this require an external service (like Redis)?"** -> If YES, reject it unless absolutely necessary.
2.  **"Does this make the Docker image larger?"** -> If YES, justify the value added.
3.  **"Does this assume 100 concurrent users?"** -> If YES, you are optimizing for the wrong target. Optimize for **1 user doing 100 things sequentially**, not 100 users doing 1 thing.

## 6. Quick Reference

- **Install:** `pip install .` (Not requirements.txt)
- **Run Dev:** `python app/app.py`
- **Run Prod:** `entrypoint.sh` (Gunicorn)
- **Test:** `pytest`
