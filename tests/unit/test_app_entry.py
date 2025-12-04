import importlib
import sys

# We import app.app, but we won't access it directly to avoid the 'Flask object' shadowing issue


def test_app_entry_point():
    """
    Ensures the app module can be imported and the global app instance is created.
    Reloading ensures coverage captures the top-level code execution.
    """
    # FIX: Use sys.modules to retrieve the actual module object.
    # We assign the result to 'reloaded_module' to ensure we are asserting
    # on the module itself, not the 'app' variable inside the 'app' package.
    reloaded_module = importlib.reload(sys.modules["app.app"])

    # Verify that the module contains the 'app' variable (the Flask instance)
    assert reloaded_module.app is not None
