
import os
from unittest.mock import patch
from audiobook_automated.utils import parse_bool
from audiobook_automated.config import parse_env_int
import importlib

def test_parse_bool_quoted():
    """Test parse_bool handles quoted strings."""
    assert parse_bool('"true"') is True
    assert parse_bool("'true'") is True
    assert parse_bool('"True"') is True
    assert parse_bool("'TRUE'") is True
    assert parse_bool('"1"') is True
    assert parse_bool("'1'") is True
    assert parse_bool('"false"') is False
    assert parse_bool("'0'") is False
    assert parse_bool(None) is False
    assert parse_bool(None, default=True) is True

def test_parse_env_int_quoted():
    """Test parse_env_int handles quoted strings."""
    with patch.dict(os.environ, {"TEST_INT": '"123"', "TEST_FLOAT": '"12.3"'}, clear=True):
        assert parse_env_int("TEST_INT", 0) == 123
        assert parse_env_int("TEST_FLOAT", 0) == 12
        assert parse_env_int("MISSING", 5) == 5

def test_config_parsing_quoted():
    """Test that Config strips quotes from all string variables."""
    import audiobook_automated.config

    env_vars = {
        "SECRET_KEY": '"secret"',
        "STATIC_VERSION": '"v123"',
        "SAVE_PATH_BASE": '"/tmp/data"',
        "ABS_URL": '"http://abs.local"',
        "NAV_LINK_NAME": '"My Link"',
        "DL_CLIENT": '"deluge"',
        "DL_PORT": '"8080"',
        "LOG_LEVEL": '"DEBUG"',
        "ABB_MIRRORS": '"mirror1, mirror2"',
        "MAGNET_TRACKERS": '"tracker1, tracker2"'
    }

    with patch.dict(os.environ, env_vars, clear=True):
        importlib.reload(audiobook_automated.config)
        from audiobook_automated.config import Config as ReloadedConfig

        assert ReloadedConfig.SECRET_KEY == "secret"
        assert ReloadedConfig.STATIC_VERSION == "v123"
        assert ReloadedConfig.SAVE_PATH_BASE == "/tmp/data"
        assert ReloadedConfig.ABS_URL == "http://abs.local"
        assert ReloadedConfig.NAV_LINK_NAME == "My Link"
        assert ReloadedConfig.DL_CLIENT == "deluge"
        assert ReloadedConfig.DL_PORT == "8080"
        assert ReloadedConfig.LOG_LEVEL_STR == "DEBUG"
        assert ReloadedConfig.ABB_MIRRORS == ["mirror1", "mirror2"]
        assert ReloadedConfig.MAGNET_TRACKERS == ["tracker1", "tracker2"]

def test_config_parsing_defaults():
    """Test defaults when env vars are missing."""
    import audiobook_automated.config

    with patch.dict(os.environ, {"SAVE_PATH_BASE": "/tmp", "DL_CLIENT": "test"}, clear=True):
        importlib.reload(audiobook_automated.config)
        from audiobook_automated.config import Config as ReloadedConfig

        assert ReloadedConfig.ABS_URL is None
        assert ReloadedConfig.NAV_LINK_NAME is None
        assert ReloadedConfig.DL_PORT is None
