"""Test the application entry point."""

from unittest.mock import MagicMock, patch


def test_app_creation():
    """Test that importing app creates the Flask instance."""
    # We mock create_app to verify it's called and to prevent side effects
    # during this specific import test if the global mocks fail (though they shouldn't).
    # However, since app.py is already imported or will be imported, we might need reload.

    import importlib
    import sys

    # Ensure we start fresh
    if "audiobook_automated.app" in sys.modules:
        del sys.modules["audiobook_automated.app"]

    with patch("audiobook_automated.create_app") as mock_create:
        mock_create.return_value = MagicMock()

        from audiobook_automated import app
        importlib.reload(app)

        # We verify that create_app was called
        mock_create.assert_called()
        # And that app.app exists (which is the result of create_app)
        assert app.app is not None
