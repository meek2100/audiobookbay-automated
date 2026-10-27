<!-- File: docs/agents/testing-quality.md -->

# Testing & Code Quality Standards

## Quality Gates & Tooling
- 100% Test Coverage: Strictly enforced with `--cov-fail-under=100`.
- Type Checking: Dual validation via MyPy and Pyright in strict mode. Use Python 3.12+ generic syntax (`def fn[T](x: T) -> T`).
- Linting & Security: Enforced via Ruff (`ruff check`, `ruff format`).
- Docstrings: Google style conventions strictly checked with `pydocstyle`. All test functions and classes require docstrings.

## Test Suite Principles
- Fixtures and contexts: Shared fixtures reside in `tests/conftest.py`. App context is pushed automatically.
- No redundant test files: Consolidate new test cases into existing domain suites (`tests/test_api.py`, `tests/test_network.py`) rather than introducing one-off files.
- Mocking: Always mock network calls and `time.sleep`.
- Frontend Tests: Executed with Jest and JSDOM (`npx jest`). Load scripts via `eval()` in `jest.setup.js`.
