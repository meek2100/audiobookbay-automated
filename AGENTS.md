<!-- File: AGENTS.md -->

# Developer & AI Agent Guide

## 1. Project Overview & Intent
- **What:** A single-user, self-hosted web appliance automating audiobook search, scraping, and torrent client dispatch.
- **Architecture:** Python 3.13/3.14 Flask backend with Gunicorn (`WORKERS=1`, `THREADS=8+`), plain ES6 browser frontend, and torrent client plugins.
- **Appliance Philosophy:** Zero SQL databases, zero local persistent application caches, and zero external queues (no Redis/Celery). Torrent clients hold download state; proxy scrapers protect user privacy.

## 2. Essential Commands
~~~bash
# Install package with development dependencies
pip install -e ".[dev]"

# Run development server
python audiobook_automated/app.py

# Execute full Python test suite with 100% coverage
pytest

# Execute frontend JavaScript unit tests
npx jest

# Run all static analysis, linting, formatting, and type checks
pre-commit run --all-files
~~~

## 3. Core Invariants (Non-Negotiable)
- **Safety Over Speed:** Mandatory random jitter sleeps (0.5–1.5s) on external requests must never be removed or reduced.
- **Concurrency Caps:** Scraper concurrency is bounded by `GLOBAL_REQUEST_SEMAPHORE` (matching `SCRAPER_THREADS`). Never bypass or increase.
- **Worker Limits:** Gunicorn must run with `WORKERS=1`. Never scale worker processes without an external rate-limit backend.
- **Zero Raw Network/Print:** Never call `requests` directly (use `audiobook_automated/scraper/network.py`). Never use `print()` (use configured logger).
- **Code Block Formatting:** Always format Markdown code blocks using triple tildes (`~~~`) rather than triple backticks.
- **First-Line File Headers:** The first line of every source file must comment the relative file path prefixed with `File:` (e.g., `# File: audiobook_automated/app.py`).

## 4. Operating Protocol & Reasoning Framework
- **Sandbox Protocol:**
  - `.agents/docs/`: Architectural documentation, research, and `plan.md`.
  - `.agents/scratchpad/`: Working drafts, isolated verification tests, and experiments.
  - `.agents/logs/`: Step-by-step reasoning and audit logs.
  - Changes must be staged and validated in `.agents/` before modifying source files.
- **Reasoning Framework:**
  - Apply Sequential Thinking and the Hermeneutic Circle against overall architecture.
  - Follow ReAct (Thought -> Action -> Observation) and Chain of Verification (CoVe).
  - Negative constraints: No placeholders, no unprompted apologies, no conversational summaries unless requested.
- **Definition of Done:** Plan documented in `.agents/docs/plan.md`, code validated in `.agents/scratchpad/`, deployment summary presented, and deployment permission requested.

## 5. Progressive Disclosure Guides
Consult specialized documentation for subsystem implementation details:
- [Architecture & Concurrency](file:///home/agentsvc/repos/audiobookbay-automated/docs/agents/architecture.md): Single-user constraints, thread-local sessions, shutdown signals.
- [Scraping Safety & Filesystem](file:///home/agentsvc/repos/audiobookbay-automated/docs/agents/scraping-safety.md): Mirror probes, fail-fast rules, negative caching, path length safety.
- [Torrent Client Strategies](file:///home/agentsvc/repos/audiobookbay-automated/docs/agents/torrent-clients.md): Strategy interface, progress normalization, client quirks, plugin creation.
- [Testing & Quality Standards](file:///home/agentsvc/repos/audiobookbay-automated/docs/agents/testing-quality.md): 100% coverage enforcement, MyPy/Pyright strict typing, fixture conventions.
