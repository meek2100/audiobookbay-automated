import importlib

import app.app


def test_app_entry_point():
    """
    Ensures the app module can be imported and the global app instance is created.
    Reloading ensures coverage captures the top-level code execution.
    """
    importlib.reload(app.app)
    assert app.app.app is not None
