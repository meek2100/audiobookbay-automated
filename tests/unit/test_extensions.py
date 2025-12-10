"""Unit tests for the Extensions module."""

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.extensions import ScraperExecutor


def test_executor_submit_without_init_raises() -> None:
    """Test that submitting a task before initialization raises RuntimeError."""
    executor = ScraperExecutor()
    with pytest.raises(RuntimeError) as exc:
        executor.submit(print, "hello")
    assert "Executor not initialized" in str(exc.value)


def test_executor_init_and_submit() -> None:
    """Test that the executor initializes and accepts tasks."""
    app = Flask(__name__)
    app.config["SCRAPER_THREADS"] = 1

    executor = ScraperExecutor()
    executor.init_app(app)

    # Simple callable to test execution
    def simple_task(x: int) -> int:
        return x * 2

    future = executor.submit(simple_task, 5)
    assert future.result() == 10

    executor.shutdown()


def test_executor_shutdown() -> None:
    """Test that shutdown is proxied to the internal ThreadPoolExecutor."""
    app = Flask(__name__)
    executor = ScraperExecutor()
    executor.init_app(app)

    # Mock the internal executor to verify shutdown call
    # We ignore the type error because we are strictly testing the proxy behavior here
    # Robust ignore pattern used to handle environments where MagicMock assignment isn't flagged
    executor._executor = MagicMock()  # type: ignore[assignment, unused-ignore]

    executor.shutdown(wait=False)

    # Verify the underlying shutdown was called with correct args
    executor._executor.shutdown.assert_called_once_with(wait=False)
