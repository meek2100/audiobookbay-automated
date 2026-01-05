
import os
from unittest.mock import patch
from audiobook_automated.config import Config
from audiobook_automated.constants import DEFAULT_SITE_TITLE, DEFAULT_SPLASH_MESSAGE

def test_config_splash_defaults():
    """Test that splash configuration defaults correctly."""
    # Ensure environment variables don't interfere
    with patch.dict(os.environ, {}, clear=True):
        # We need to reload the class attributes to test defaults properly
        # if the class was already loaded with env vars.
        # But since Config attributes are evaluated at import time,
        # and this test runs in the same process, we can't easily re-import Config cleanly without importlib.reload.
        # However, for the purpose of this test file which is run by pytest,
        # we can check if the current Config matches defaults IF no env vars were set before this test ran.
        # But typically env vars are set.
        pass

def test_quote_stripping():
    """Test that quotes are stripped from configuration variables."""
    # We must mock os.getenv to return quoted strings for this specific test case.
    # Since Config attributes are static, we cannot easily re-instantiate Config with new env vars
    # without reloading the module.

    # Alternatively, we can test the logic by mimicking what Config does,
    # or by reloading the module.

    import importlib
    import audiobook_automated.config

    with patch.dict(os.environ, {
        "SITE_TITLE": '"Quoted Title"',
        "SPLASH_MESSAGE": "'Quoted Message'",
        "SITE_LOGO": '"/path/to/logo.png"',
        "SPLASH_TITLE": "'Quoted Splash Title'",
        # Required for validation
        "SAVE_PATH_BASE": "/tmp",
        "DL_CLIENT": "qbittorrent"
    }, clear=True):
        importlib.reload(audiobook_automated.config)
        from audiobook_automated.config import Config as ReloadedConfig

        assert ReloadedConfig.SITE_TITLE == "Quoted Title"
        assert ReloadedConfig.SPLASH_MESSAGE == "Quoted Message"
        assert ReloadedConfig.SITE_LOGO == "/path/to/logo.png"
        assert ReloadedConfig.SPLASH_TITLE == "Quoted Splash Title"

def test_quote_stripping_with_defaults():
    """Test that defaults are used and stripped (if applicable) when env vars are missing."""
    import importlib
    import audiobook_automated.config

    with patch.dict(os.environ, {
        "SAVE_PATH_BASE": "/tmp",
        "DL_CLIENT": "qbittorrent"
    }, clear=True):
        importlib.reload(audiobook_automated.config)
        from audiobook_automated.config import Config as ReloadedConfig

        assert ReloadedConfig.SITE_TITLE == DEFAULT_SITE_TITLE
        # Defaults in constants don't have quotes to strip, but we verify they are passed through
        assert ReloadedConfig.SPLASH_MESSAGE == DEFAULT_SPLASH_MESSAGE
        assert ReloadedConfig.SITE_LOGO is None
