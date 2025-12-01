import unittest
from unittest.mock import MagicMock, patch

from app.healthcheck import health_check


class TestHealthCheck(unittest.TestCase):
    @patch("app.healthcheck.urllib.request.urlopen")
    @patch("app.healthcheck.sys.exit")
    def test_health_check_success(self, mock_exit, mock_urlopen):
        # Simulate HTTP 200
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        health_check()

        # Should exit with 0 (Success)
        mock_exit.assert_called_with(0)

    @patch("app.healthcheck.urllib.request.urlopen")
    @patch("app.healthcheck.sys.exit")
    def test_health_check_failure_500(self, mock_exit, mock_urlopen):
        # Simulate HTTP 500
        mock_response = MagicMock()
        mock_response.status = 500
        mock_urlopen.return_value.__enter__.return_value = mock_response

        health_check()

        # Should exit with 1 (Failure)
        mock_exit.assert_called_with(1)

    @patch("app.healthcheck.urllib.request.urlopen")
    @patch("app.healthcheck.sys.exit")
    def test_health_check_exception(self, mock_exit, mock_urlopen):
        # Simulate Connection Refused
        mock_urlopen.side_effect = Exception("Connection refused")

        health_check()

        # Should exit with 1 (Failure)
        mock_exit.assert_called_with(1)
