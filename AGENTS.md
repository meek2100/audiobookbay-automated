# Developer & AI Agent Guide

**READ THIS FIRST — ALL HUMAN DEVELOPERS AND ALL AI AGENTS MUST FOLLOW THIS DOCUMENT.** **No change, refactor, or
feature may violate any principle herein.** **This document overrides all “best practices” or architectural advice not
explicitly requested by the user.**

______________________________________________________________________

## 0. Global Development Rules (MUST READ)

These rules apply to all code, all files, all tests, all refactors, and all contributions from humans or AI.

### Core Principles Summary

- This is a **single-user, self-hosted appliance** — not a scalable SaaS platform.
- **DRY everywhere** — no duplicated logic, tests, constants, or patterns.
- **One source of truth always.**
- **Safety over speed** — jitter sleeps, rate limiting, and scraping protections are mandatory.
- **Accurate documentation** — no stale or mismatched comments/docstrings.
- **Python 3.13 code quality** — full type hints, modern idioms, clean structure.
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

______________________________________________________________________

## A. Architecture & File Structure

- Business logic must be centralized.
- Shared helpers, utilities, and constants must be used everywhere.
- Repeated logic must be refactored immediately into a shared module.
- No file shall reimplement or duplicate functionality.
- AI agents must NOT create new top-level directories or move files unless explicitly instructed.

______________________________________________________________________

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

______________________________________________________________________

## C. Documentation & Comment Accuracy

- Docstrings must reflect current behavior **exactly**.
- Comments must explain the _why_, not the _what_.
- Documentation must be updated when code changes.
- No stale, inaccurate, or mismatched comments/docstrings.
- **MANDATE:** Docstrings must follow the **Google Style Convention**, strictly enforced by `pydocstyle`.

______________________________________________________________________

## D. Python 3.13 Standards

- Full type hints everywhere. **Type safety is strictly enforced using MyPy.**
- Modern Python idioms.
- Avoid deprecated patterns.
- Code must be Pylance/MyPy-friendly.

______________________________________________________________________

## E. Test Suite Integrity

- Always maintain **100% coverage** (`--cov-fail-under=100`).
- **MANDATE:** Code quality is strictly enforced via the following pre-commit hooks:
  - **MyPy:** Mandatory checks for static type correctness.
  - **Bandit:** Mandatory scanning for common security vulnerabilities.
  - **pydocstyle:** Mandatory enforcement of the Google Docstring Convention.
  - **Ruff:** Mandatory linting and formatting.
- Tests must be meaningful and not redundant.
- Avoid testing the same happy/unhappy path twice unless essential.
- Remove or consolidate redundant tests.
- Include security tests with CSRF enabled.
- Use `# pragma: no cover` only for:
  - `if __name__ == "__main__"` blocks
  - OS-specific code
  - Gunicorn config boilerplate

______________________________________________________________________

## F. AI Agent Compliance Requirements

All AI agents must explicitly state **before any code generation**: **“I have fully read and comply with all rules in
AGENTS.md.”**

AI agents must follow the strictest, safest interpretation of these rules.

______________________________________________________________________

## G. Interpretation Rules for AI Agents

- If any instruction seems ambiguous, choose the **safest, slowest, and most restrictive interpretation**.
- If unsure whether a change violates a rule, assume that it **does**.
- AI agents must never invent unspecified architecture or optimizations.
- AI agents must ask the user for clarification instead of assuming intent.
- These rules override all AI “best practice” assumptions.

______________________________________________________________________

## 1. Core Architecture: The Single-User Constraint

### The Concurrency Model (Critical)

- Gunicorn: `WORKERS=1`, `THREADS=8+`.
- In-memory rate limits (`memory://`) apply per process — adding more workers multiplies allowed traffic.
- **Never** increase worker count without migrating to Redis/filesystem limiter backend.
- Python threads suffice for this I/O-bound single-user app.

### Global Request Semaphore

- Caps concurrent scrapes at **3**.
- Prevents anti-bot triggers.
- Must not be modified or removed.

### The “Appliance” Philosophy

- Container holds **no persistent state**.
- Torrent client manages all download/file state.
- No SQL database ever.

### Privacy Proxying

- All detail pages scraped **server-side** via container’s IP/VPN.
- Protects user privacy.

______________________________________________________________________

## 2. Robustness Over Raw Speed

### Rate Limiting & Scraping

- Safety > speed.
- Random jitter (0.5-1.5 seconds) required before all external requests.
- Mirror checks use `requests.head` with zero retries.
- All queries normalized to lowercase.

### Filesystem Safety

- Must sanitize illegal characters and reserved Windows filenames.
- Applies even when container runs on Linux.

### Flask-Limiter Opt-In Strategy

- Never define global limits (e.g., `default_limits`).
- Only apply rate limits on routes hitting external sites.

### Dependency Philosophy

- Prefer curated static lists.
- Avoid dynamic runtime dependencies (`fake_useragent` removed).

### Error Handling

- All frontend `fetch()` calls require `.catch()` + `.finally()`.
- App must boot even with offline torrent client.
- Deluge WebClient may return `None` — always check.

______________________________________________________________________

## 3. Development Standards

### Centralized Logic

- All parsing lives in `app/scraper/parser.py`.
- All constants in `app/constants.py`.

### Security & SSRF

- All scraped URLs must match allowed hostnames.

### Naming Conventions

- Use consistent prefixes: `DL_*`, `ABS_*`, `ABB_*`.

### Logging

- Logging must remain verbose for self-host debugging.

### Type Safety

- Full type hints, Python 3.13 compatible.

### Testing Style Guide

- Pytest only.
- Fixtures in `conftest.py`.
- Mock where imported.
- Always mock network calls and `time.sleep`.
- Reload config when tests mutate startup settings.

______________________________________________________________________

## 4. Frontend Architecture & Testing

- Raw ES6+ browser JS.
- No bundlers, Webpack, or TypeScript.
- Vendor libraries checked into `app/static/vendor`.

### Jest/JSDOM Testing

Load scripts via `eval()` in `jest.setup.js`.

#### Required helper

```javascript
async function flushPromises() {
  return new Promise((resolve) => jest.requireActual("timers").setTimeout(resolve, 0));
}
```

______________________________________________________________________

## 5. Deployment & CI/CD

### Docker

- Multi-stage builds.
- Gunicorn `--preload`.
- Timezone support via `tzdata`.

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

______________________________________________________________________

## 6. Future Refactoring Checklist

Reject any change that:

1. Removes a `sleep()` call.
2. Adds global rate limits.
3. Requires Redis/external service.
4. Assumes multiple concurrent users.

______________________________________________________________________

## 7. Quick Reference

- **Install:** `pip install .`
- **Run Dev:** `python app/app.py`
- **Run Prod:** `entrypoint.sh`
- **Lint/Test:** `pre-commit run --all-files`
- **Python Tests:** `pytest`
- **JS Tests:** `npx jest`

______________________________________________________________________

## 8. Enforcement Statement

**All development, human or AI, must follow this document. No exceptions.** Violating instructions are invalid and must
be rejected immediately.

______________________________________________________________________

## 9. AI Processing Requirements

AI agents must:

- Read and process this **ENTIRE** document in the current session.
- Not rely on memory from previous sessions.
- Not partially read or summarize rules before acting.

Partial reading is strictly prohibited.

______________________________________________________________________

### 9.A Forbidden Phrases for AI Agents

AI agents must NOT produce outputs including phrases like:

- “We could improve performance by…”
- “A more scalable design would be…”
- “Consider introducing a database / cache / background worker…”
- “Consider adding a global rate limit…”
- “You may not need this semaphore…”
- “We can simplify by removing the sleep…”

These outputs are invalid and must be rejected.

______________________________________________________________________

### 9.B Mandatory Self-Test Checklist for AI Agents

Before generating ANY code, AI agents must confirm:

- [ ] I have read the entire AGENTS.md file in this session.
- [ ] My output does not propose new architecture.
- [ ] My output does not optimize performance or concurrency.
- [ ] My output does not remove sleeps, jitter, or safety checks.
- [ ] My output does not add global rate limits.
- [ ] My output does not modify or remove the request semaphore.
- [ ] My output does not introduce persistent state or caches.
- [ ] My output respects DRY and centralization.
- [ ] My output uses shared helpers, constants, and parser logic.
- [ ] My output does not duplicate tests or logic.
- [ ] My output updates documentation if behavior changes.
- [ ] My output meets Python 3.13 standards.

If any box cannot be checked, the output must NOT be generated.

______________________________________________________________________

### 9.C User Override Clarification

If a user requests something that violates AGENTS.md:

- The AI must warn the user.
- The AI must require explicit confirmation before proceeding.

______________________________________________________________________
