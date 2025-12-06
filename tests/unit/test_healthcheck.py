from typing import Any
from unittest.mock import MagicMock, patch

from app.healthcheck import health_check


@patch("app.healthcheck.urllib.request.urlopen")
@patch("app.healthcheck.sys.exit")
def test_health_check_success(mock_exit: Any, mock_urlopen: Any) -> None:
    # Simulate HTTP 200
    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    health_check()

    # Should exit with 0 (Success)
    mock_exit.assert_called_with(0)


@patch("app.healthcheck.urllib.request.urlopen")
@patch("app.healthcheck.sys.exit")
def test_health_check_failure_500(mock_exit: Any, mock_urlopen: Any) -> None:
    # Simulate HTTP 500
    mock_response = MagicMock()
    mock_response.status = 500
    mock_urlopen.return_value.__enter__.return_value = mock_response

    health_check()

    # Should exit with 1 (Failure)
    mock_exit.assert_called_with(1)


@patch("app.healthcheck.urllib.request.urlopen")
@patch("app.healthcheck.sys.exit")
def test_health_check_exception(mock_exit: Any, mock_urlopen: Any) -> None:
    # Simulate Connection Refused
    mock_urlopen.side_effect = Exception("Connection refused")

    health_check()

    # Should exit with 1 (Failure)
    mock_exit.assert_called_with(1)


@patch("app.healthcheck.os.getenv")
@patch("app.healthcheck.urllib.request.urlopen")
@patch("app.healthcheck.sys.exit")
def test_health_check_host_0000(mock_exit: Any, mock_urlopen: Any, mock_getenv: Any) -> None:
    """Test mapping 0.0.0.0 to 127.0.0.1"""
    # Simulate LISTEN_HOST=0.0.0.0
    mock_getenv.side_effect = lambda key, default=None: "0.0.0.0" if key == "LISTEN_HOST" else default

    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    health_check()

    # Verify urlopen was called with 127.0.0.1
    args, _ = mock_urlopen.call_args
    assert "http://127.0.0.1" in args[0]
    mock_exit.assert_called_with(0)


@patch("app.healthcheck.os.getenv")
@patch("app.healthcheck.urllib.request.urlopen")
@patch("app.healthcheck.sys.exit")
def test_health_check_host_ipv6(mock_exit: Any, mock_urlopen: Any, mock_getenv: Any) -> None:
    """Test mapping [::] to [::1]"""
    # Simulate LISTEN_HOST=[::]
    mock_getenv.side_effect = lambda key, default=None: "[::]" if key == "LISTEN_HOST" else default

    mock_response = MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_response

    health_check()

    # Verify urlopen was called with [::1]
    args, _ = mock_urlopen.call_args
    assert "http://[::1]" in args[0]
    mock_exit.assert_called_with(0)
