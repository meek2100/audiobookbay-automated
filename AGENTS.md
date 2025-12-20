<!-- File: AGENTS.md -->

# Developer & AI Agent Guide

**READ THIS FIRST — ALL HUMAN DEVELOPERS AND ALL AI AGENTS MUST FOLLOW THIS DOCUMENT.** **No change, refactor, or
feature may violate any principle herein.** **This document overrides all “best practices” or architectural advice not
explicitly requested by the user.**

---

## 0. Global Development Rules (MUST READ)

These rules apply to all code, all files, all tests, all refactors, and all contributions from humans or AI.

### Core Principles Summary

- This is a **single-user, self-hosted appliance** — not a scalable SaaS platform.
- **DRY everywhere** — no duplicated logic, tests, constants, or patterns.
- **One source of truth always.**
- **Safety over speed** — jitter sleeps, rate limiting, and scraping protections are mandatory.
- **Accurate documentation** — no stale or mismatched comments/docstrings.
- **Python 3.14 code quality** — full type hints, modern idioms (e.g., `pathlib`), clean structure.
- **100% test coverage** — but tests must not be redundant.
- **Frontend must stay simple** — no bundlers, no frameworks, no unnecessary complexity.

### Hard Prohibitions (NEVER DO THESE)

- Do NOT remove or reduce jitter sleeps.
- Do NOT add global rate limits beyond those documented.
- Do NOT apply global default rate limits (Flask-Limiter must remain opt-in only).
- Do NOT add external services (Redis, Celery, databases).
- Do NOT add more Gunicorn workers.
- Do NOT modify, remove, bypass, or increase the **GLOBAL_REQUEST_SEMAPHORE** or concurrency safeguards.
- Do NOT create or use an internal SQL database.
- Do NOT introduce server-side state, sessions, persistent caches, or any form of local data storage.
- Do NOT duplicate any logic that already exists.
- Do NOT bypass centralized helper modules.
- Do NOT alter scraper safety mechanisms or request limits.
- Do NOT optimize for multi-user throughput.
- Do NOT reorganize directories or create new top-level modules without explicit user instruction.

### Markdown Formatting Rule (CRITICAL)

- **Use Tildes for Code Blocks:** All code blocks in Markdown files (including this one) **MUST** use triple tildes
  (`~~~`) instead of triple backticks.
  - **Why:** This prevents rendering conflicts when AI agents generate Markdown files inside a chat interface (which
    uses backticks for its own formatting).
  - **Example:** Use `~~~python` instead of ` ```python `.

---

## A. Architecture & File Structure

- Business logic must be centralized.
- Shared helpers, utilities, and constants must be used everywhere.
- Repeated logic must be refactored immediately into a shared module.
- No file shall reimplement or duplicate functionality.
- AI agents must NOT create new top-level directories or move files unless explicitly instructed.
- **Client Architecture:** Torrent Clients must be implemented using the **Strategy Pattern** (see
  `audiobook_automated/clients.py`). `TorrentManager` acts as the facade and must not contain client-specific
  implementation details.

---

## B. DRY & Single Source of Truth

- Before writing new logic, search the repo for an existing implementation.
- Consolidate duplication proactively.
- Use `parser.py`, `utils`, and `constants` exclusively for shared behavior.

## B.1 Single Source of Truth Priority Order

When information appears in multiple places, the authoritative source is:

1. **AGENTS.md (this file)**
2. **Constants (`constants.py`)**
3. **Shared helpers (`utils`, `scraper/parser.py`)**
4. **Environment variables / runtime config**
5. **Docstrings and inline comments**
6. **Function or method body**

Any lower-priority source conflicting with a higher one must be updated or removed.

---

## C. Documentation & Comment Accuracy

- Docstrings must reflect current behavior **exactly**.
- Comments must explain the _why_, not the _what_.
- Documentation must be updated when code changes.
- No stale, inaccurate, or mismatched comments/docstrings.
- **MANDATE:** Docstrings must follow the **Google Style Convention**, strictly enforced by `pydocstyle`.
- **File Headers:** The first line of every source file MUST be a comment containing the file path relative to the
  project root, prefixed with File: (e.g., `# File: audiobook_automated/app.py` or `// File: static/js/search.js`).
  - **Exception:** If the file requires a Shebang (e.g., `#!/bin/bash`), the file path comment must be on the second
    line.
  - **Exception:** Strictly formatted JSON files (e.g., `package.json`) must NOT include comments.

---

## D. Python 3.14 Standards

- Full type hints everywhere. **Type safety is strictly enforced using MyPy.**
- Modern Python idioms. **Use `pathlib` instead of `os.path` for filesystem operations.**
- Avoid deprecated patterns.
- Code must be Pylance/MyPy-friendly.
- **Type Separation:** Use `BookSummary` for search results and `BookDetails` for full book info. Do not mix them.
  `BookDetails` must enforce fields like `description`, `trackers`, and `info_hash`.

---

## E. Test Suite Integrity

- Always maintain **100% coverage** (`--cov-fail-under=100`).
- **MANDATE:** Code quality is strictly enforced via the following pre-commit hooks:
  - **MyPy:** Mandatory checks for static type correctness.
  - **Ruff (Security):** Mandatory scanning for common security vulnerabilities (replacing Bandit).
  - **pydocstyle:** Mandatory enforcement of the Google Docstring Convention.
  - **Ruff (Lint/Format):** Mandatory linting and formatting.
- **Mandatory Docstrings:** All test functions and classes MUST include a docstring explaining the test case. Do not
  exclude tests from `pydocstyle` checks.
- Tests must be meaningful and not redundant.
- Avoid testing the same happy/unhappy path twice unless essential.
- Remove or consolidate redundant tests.
- **Test File Consolidation (MANDATORY):** Do NOT create new "one-off" test files (e.g., `test_api_invalid.py`,
  `test_network_malformed.py`) when an existing test file covers that domain.
  - Merge edge cases, error conditions, and new features into the primary test file (e.g., `test_api.py`,
    `test_network.py`).
  - Keep the `tests/` directory clean, organized, and structurally mirrored to the source code.
- Include security tests with CSRF enabled.
- Use `# pragma: no cover` only for:
  - `if __name__ == "__main__"` blocks
  - OS-specific code
  - Gunicorn config boilerplate

---

## F. AI Agent Compliance Requirements

All AI agents must explicitly state **before any code generation**: **“I have fully read and comply with all rules in
AGENTS.md.”**

AI agents must follow the strictest, safest interpretation of these rules.

---

## G. Interpretation Rules for AI Agents

- If any instruction seems ambiguous, choose the **safest, slowest, and most restrictive interpretation**.
- If unsure whether a change violates a rule, assume that it **does**.
- AI agents must never invent unspecified architecture or optimizations.
- AI agents must ask the user for clarification instead of assuming intent.
- These rules override all AI “best practice” assumptions.

---

## H. Extension Guidelines: Adding New Torrent Clients

The application supports a **Plugin Architecture** for torrent clients. Developers can add support for new clients
without modifying the core codebase.

### H.1 Implementation Steps

1. **Use the Template:** Copy `audiobook_automated/clients/client_template.py` to a new file (e.g.,
   `audiobook_automated/clients/rtorrent.py`).
2. **Implement the Interface:** Your class must inherit from `TorrentClientStrategy` and implement all abstract methods.
3. **Define Defaults:** You MUST set the `DEFAULT_PORT` class attribute to the standard port for that client.
4. **Configuration:** The `TorrentManager` will automatically load your plugin if the `DL_CLIENT` environment variable
   matches your filename (minus extension).

### H.2 Deployment (Drop-in)

For self-hosted setups using Docker, users can "drop in" a new client:

1. Create the python file (e.g., `myclient.py`).
2. Mount it into the container: `-v /path/to/myclient.py:/app/audiobook_automated/clients/myclient.py`.
3. Set `DL_CLIENT=myclient`.
4. Restart the container.

---

## 1. Core Architecture: The Single-User Constraint

### The Concurrency Model (Critical)

- Gunicorn: `WORKERS=1`, `THREADS=8+`.
- In-memory rate limits (`memory://`) apply per process — adding more workers multiplies allowed traffic.
- **Never** increase worker count without migrating to Redis/filesystem limiter backend.
- Python threads suffice for this I/O-bound single-user app.

### Thread Safety (Critical)

- **Stateful objects must be thread-local or isolated.**
- `requests.Session` and Torrent Client instances must **never** be shared across threads.
- Use `threading.local()` or instantiate per-task/per-request.
- **MANDATE:** Subclass `threading.local` for typed thread-local storage (e.g., `class ClientLocal(threading.local)`) to
  ensure MyPy compliance.
- **Why:** Shared sessions cause race conditions, connection resets, and data corruption in threaded environments.

### Global Request Semaphore

- Caps concurrent scrapes to the configured limit (`SCRAPER_THREADS`).
- Prevents anti-bot triggers.
- Must not be modified or removed without careful consideration of external rate limits.
- **Note:** The application allows configuring the worker thread pool size (via `SCRAPER_THREADS`). The global semaphore
  **MUST** be initialized to match this value at startup (in `audiobook_automated/__init__.py`) to ensures that the
  thread pool does not exceed the allowed concurrency for external requests.

### The “Appliance” Philosophy

- Container holds **no persistent state**.
- Torrent client manages all download/file state.
- No SQL database ever.

### Privacy Proxying

- All detail pages scraped **server-side** via container’s IP/VPN.
- Protects user privacy.

### Global Concurrency Controls

- **Global Request Semaphore:** Caps concurrent scrapes at `SCRAPER_THREADS`.
- **Cache Locks:** Shared memory caches must be guarded by thread locks to prevent race conditions during concurrent
  reads/writes.

---

## 2. Robustness Over Raw Speed

### Production Hardening (New)

- **Strict Dependency Pinning:** All dependencies (production AND development) in `pyproject.toml` MUST be pinned to
  exact versions (e.g., `requests==2.32.3`, not `>=`) to prevent transitive dependency breakage and ensure reproducible
  CI builds.
- **Explicit Timeouts:** All blocking I/O calls (requests, socket operations) MUST have an explicit constant defined in
  `constants.py` (e.g., `ABS_TIMEOUT_SECONDS`). Magic number timeouts are prohibited.
- **Dockerfile Build Order:** The Dockerfile MUST copy `pyproject.toml` and `audiobook_automated/` (the source code)
  **BEFORE** running `pip install .`. Failure to do so results in an empty package installation.
- **Static Asset Versioning:** The `Dockerfile` MUST execute
  `python3 -m audiobook_automated.utils > audiobook_automated/version.txt` during the build process. The application
  logic must prioritize reading this file at startup to prevent expensive filesystem traversal.

### Rate Limiting & Scraping

- Safety > speed.
- Random jitter (0.5-1.5 seconds) required before all external requests.
- Mirror checks use `requests.head` with zero retries.
- **Fail Fast:** Mirror checks must return `None` immediately upon `Timeout` or `ConnectionError`.
- **Method Fallback:** If `HEAD` returns 405 (Method Not Allowed) or 403 (Forbidden), the check **MUST** fall back to a
  `GET` request.
- All queries normalized to lowercase.
- **Search Query Safety:** All search endpoints must enforce a minimum query length (e.g., 2 characters) to prevent
  spamming the scraper with broad queries.
- **Session Reuse:** `requests.Session` objects for high-frequency operations (like ping checks) must be cached or
  thread-local to avoid expensive SSL handshake overhead.

### Filesystem Safety & Path Limits

- Must sanitize illegal characters and reserved Windows filenames.
- Reserved Filename Handling: Checks must identify reserved names even with extensions or compound extensions (e.g.,
  CON.txt and CON.tar.gz are both invalid).
- Applies even when container runs on Linux.
- **Path Length Safety (CRITICAL):**
  - Logic MUST calculate the maximum allowable directory name length dynamically based on the configured
    `SAVE_PATH_BASE`.
  - **Priority:** The OS limitation (approx. 260 chars on Windows) overrides any "aesthetic" preference for long titles.
  - If `SAVE_PATH_BASE` is deep, the application must truncate the title aggressively to prevent file system errors.
- **Collision Avoidance:** When using fallback directory names **OR** sanitized names that result in potential
  collisions (e.g., Windows reserved names like `CON` becoming `CON_Safe`), you **MUST** append a short UUID (e.g.,
  `uuid.uuid4().hex[:8]`) to guarantee uniqueness.

### Resilience & Negative Caching

- **Retry Storm Prevention:** If all external mirrors/resources fail, the application **MUST** cache this failure state
  (e.g., for 30 seconds) to prevent retry storms.
- **Do Not Clear Caches Aggressively:** Do not clear mirror caches immediately upon a search failure if doing so would
  bypass the negative caching backoff period.

### Flask-Limiter Opt-In Strategy

- Never define global limits (e.g., `default_limits`).
- Only apply rate limits on routes hitting external sites.

### Dependency Philosophy

- Prefer curated static lists.
- Avoid dynamic runtime dependencies (fake_useragent removed).
- Zero Unused Production Deps: Development tools (e.g., python-dotenv, linters) must be strictly categorized in
  [project.optional-dependencies] dev. If a library is not used in the production runtime (e.g., .env files are handled
  by Docker/Compose), it must be removed.

### Error Handling

- All frontend `fetch()` calls require `.catch()` + `.finally()`.
- App must boot even with offline torrent client.
- Deluge WebClient may return `None` — always check.
- **Deluge Warning:** The logic for detecting missing Label plugins relies on string matching error messages (e.g.
  "unknown parameter"). This is fragile; any changes to the client library must be tested against this logic.

---

## 3. Development Standards

### Startup & Configuration

- **No Silent Exits:** Critical startup errors (e.g., missing config) **MUST** `raise RuntimeError` rather than calling
  `sys.exit()`. This ensures the WSGI server (Gunicorn) captures and logs the stack trace before the worker process
  dies.
- **Validation:** Configuration must fail fast. `DL_CLIENT` and `SAVE_PATH_BASE` are mandatory.
  - `DL_CLIENT` **MUST** be set. (Use of specific client names is dynamically validated).
- **Logging Level:** The application logger must explicitly apply the configured `LOG_LEVEL` in `__init__.py`. Flask
  does not do this automatically.
- **Docker Permissions:** The application must start as `root` (PID 1) in the entrypoint to fix volume permissions via
  `chown` and `usermod`, then drop privileges to `appuser` using `gosu`.
- **Client Connectivity Check:** The application MUST attempt to verify torrent client credentials at startup (in
  `__init__.py` or `extensions.py`).
  - Failure to connect should NOT crash the app but MUST log a warning.
  - This ensures admins are alerted to misconfiguration (e.g., wrong password, missing dependency) immediately upon
    container start.

### Centralized Logic & Concurrency

- All parsing lives in `audiobook_automated/scraper/parser.py`.
- **MANDATE:** Use `lxml` parser for all BeautifulSoup operations (performance & robustness).
- All constants in `audiobook_automated/constants.py`.
- **Thread Safety:** Shared resources (e.g., `mirror_cache`, `search_cache`) and their associated locks (e.g.,
  `CACHE_LOCK`) **MUST** be defined in the same module (`audiobook_automated/scraper/network.py`) to ensure atomic
  access.

### Extension & Global Object Initialization

- **Lazy Initialization Mandate:** All global extensions (e.g., `ScraperExecutor`, `TorrentManager`) **MUST** follow the
  Flask `init_app()` pattern.
- **No Import-Time Config:** Do not bind configuration values (e.g., `SCRAPER_THREADS`) to global objects at import
  time. Values must be read strictly from `app.config` within `init_app()` or at runtime.
- **Why:** This ensures tests can override configuration (e.g., setting threads to 1) without being blocked by values
  read when the module was first imported.

### Security & SSRF

- All scraped URLs must match allowed hostnames.

### Torrent Client Strategy Rules

All Torrent Client implementations (`clients.py`) must normalize data to the **Appliance Standard** immediately upon
fetching. Future implementations must respect these specific library constraints:

- **Resource Cleanup:** All strategies must implement a `close()` method to release sockets/sessions explicitly.
- **Progress Normalization:**
  - **qBittorrent:** Returns float `0.0 - 1.0`. Must multiply by 100.
  - **Transmission:** Returns float `0.0 - 100.0`. **Do NOT** multiply by 100.
  - **Deluge:** Returns float `0.0 - 100.0`. **Do NOT** multiply by 100.
  - **Result:** All strategies must return a standard `0.0 - 100.0` float rounded to 2 decimal places.

- **Category/Label Filtering:**
  - **qBittorrent:** Supports efficient server-side filtering (`torrents_info(category=...)`). Use it.
  - **Transmission:** Does **NOT** support server-side label filtering. You **MUST** fetch all torrents and filter by
    label client-side (in Python).
  - **Deluge:** Support is conditional. You **MUST** detect if the "Label" plugin is enabled at connection time. If
    missing, fetch all torrents to ensure they are visible, even if uncategorized.

- **Add Magnet Logic:**
  - **qBittorrent:** API v2 returns JSON metadata; older versions return string "Ok."/"Fails.". Logic must handle both.
  - **Transmission:** Must handle `http` vs `https` protocols explicitly in the client constructor.
  - **Deluge:** Must handle potential "Unknown Parameter" errors if the Label plugin is missing during add.

### Naming Conventions

- Use consistent prefixes: `DL_*`, `ABS_*`, `ABB_*`.

### Logging

- Logging must remain verbose for self-host debugging.

### Type Safety

- Full type hints, Python 3.14 compatible.
- When a MyPy error appears in one environment but not another (causing 'unused type ignore' errors), use the robust
  ignore pattern: `# type: ignore[error-code, unused-ignore]`. This suppresses both the original error and the warning
  about the ignore being unused.
  - **Integer Parsing:** When parsing integer environment variables (e.g., `PAGE_LIMIT`, `SCRAPER_THREADS`), always use
    `int(float(value))` to handle float-string values (e.g. "3.0") commonly injected by container orchestrators.

### Testing Style Guide

- Pytest only.
- Fixtures in `conftest.py`.
- Mock where imported.
- Always mock network calls and `time.sleep`.
- Reload config when tests mutate startup settings.
- Ensure all tests run within an application context. Use an `autouse=True` fixture in `conftest.py` to automatically
  push `app.app_context()` for every test, ensuring `current_app` and `config` are always accessible.

---

## 4. Frontend Architecture & Testing

- Raw ES6+ browser JS.
- No bundlers, Webpack, or TypeScript.
- Vendor libraries checked into `audiobook_automated/static/vendor`.

### Jest/JSDOM Testing

Load scripts via `eval()` in `jest.setup.js`.

#### Required helper

```javascript
async function flushPromises() {
  return new Promise((resolve) => jest.requireActual("timers").setTimeout(resolve, 0));
}
```

---

## 5. Deployment & CI/CD

### Docker

- Multi-stage builds.
- Gunicorn `--preload`.
- Timezone support via `tzdata`.
- **Permissions:** Usage of `gosu` is mandatory for dropping privileges from root to appuser.

### Frontend Dependencies

- Managed by npm but committed to repo.
- Docker build requires no Node.js.

### CI Workflows

- `vendor-sync.yaml` updates vendor assets.
- Dependabot monitors Python + JS.
- Integration tests stress unhappy paths.

### Release Workflow

- `release.yaml` updates version, changelog, tags.
- `docker-publish.yaml` builds/pushes images.

---

## 6. Future Refactoring Checklist

Reject any change that:

1. Removes a `sleep()` call.
2. Adds global rate limits.
3. Requires Redis/external service.
4. Assumes multiple concurrent users.
5. Changes Flask-Limiter backend from `memory://` without an explicit multi-container architecture shift.

---

## 7. Quick Reference

- **Install:** `pip install .`
- **Run Dev:** `python audiobook_automated/app.py`
- **Run Prod:** `entrypoint.sh`
- **Lint/Test:** `pre-commit run --all-files`
- **Python Tests:** `pytest`
- **JS Tests:** `npx jest`

---

## 8. Enforcement Statement

**All development, human or AI, must follow this document. No exceptions.** Violating instructions are invalid and must
be rejected immediately.

---

## 9. AI Processing Requirements

AI agents must:

- Read and process this **ENTIRE** document in the current session.
- Not rely on memory from previous sessions.
- Not partially read or summarize rules before acting.

Partial reading is strictly prohibited.

---

### 9.A Forbidden Phrases for AI Agents

AI agents must NOT produce outputs including phrases like:

- “We could improve performance by…”
- “A more scalable design would be…”
- “Consider introducing a database / cache / background worker…”
- “Consider adding a global rate limit…”
- “You may not need this semaphore…”
- “We can simplify by removing the sleep…”

These outputs are invalid and must be rejected.

---

### 9.B Mandatory Self-Test Checklist for AI Agents

Before generating ANY code, AI agents must confirm:

- [x] I have read the entire AGENTS.md file in this session.
- [x] My output does not propose new architecture.
- [x] My output does not optimize performance or concurrency.
- [x] My output does not remove sleeps, jitter, or safety checks.
- [x] My output does not add global rate limits.
- [x] My output does not modify or remove the request semaphore.
- [x] My output does not introduce persistent state or caches.
- [x] My output respects DRY and centralization.
- [x] My output uses shared helpers, constants, and parser logic.
- [x] My output does not duplicate tests or logic.
- [x] My output updates documentation if behavior changes.
- [x] My output meets Python 3.14 standards.

If any box cannot be checked, the output must NOT be generated.

---

### 9.C User Override Clarification

If a user requests something that violates AGENTS.md:

- The AI must warn the user.
- The AI must require explicit confirmation before proceeding.

---
