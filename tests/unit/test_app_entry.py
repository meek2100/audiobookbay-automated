import importlib
import sys

# We import app.app, but we won't access it directly to avoid the 'Flask object' shadowing issue
# We must ensure it is imported at least once before reloading sys.modules key.


def test_app_entry_point() -> None:
    """Ensures the app module can be imported and the global app instance is created.

    Reloading ensures coverage captures the top-level code execution.
    """
    # FIX: Use sys.modules to retrieve the actual module object.
    # We assign the result to 'reloaded_module' to ensure we are asserting
    # on the module itself, not the 'app' variable inside the 'app' package.
    # Check if loaded, if not import it
    if "audiobook_automated.app" not in sys.modules:
        importlib.import_module("audiobook_automated.app")

    reloaded_module = importlib.reload(sys.modules["audiobook_automated.app"])

    # Verify that the module contains the 'app' variable (the Flask instance)
    assert reloaded_module.app is not None
