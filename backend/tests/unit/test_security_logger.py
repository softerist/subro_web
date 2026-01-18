# backend/tests/unit/test_security_logger.py
"""
Unit tests for security_logger passkey methods.
"""

from unittest.mock import patch

from app.core.security_logger import security_log


def test_passkey_failed_logs_correctly():
    """Test that passkey_failed logs the correct format for fail2ban."""
    with patch.object(security_log.logger, "info") as mock_info:
        security_log.passkey_failed("192.168.1.100")

        # Verify the log call
        mock_info.assert_called_once()
        call_args = mock_info.call_args[0][0]

        # Should contain PASSKEY_FAILED and the IP
        assert "PASSKEY_FAILED]" in call_args
        assert "ip=192.168.1.100" in call_args


def test_passkey_failed_sanitizes_ip():
    """Test that passkey_failed sanitizes malicious IP input."""
    with patch.object(security_log.logger, "info") as mock_info:
        # Try to inject newlines or control characters
        security_log.passkey_failed("192.168.1.100\n<script>alert(1)</script>")

        # Verify sanitization happened
        call_args = mock_info.call_args[0][0]
        assert "\n" not in call_args
        assert "<script>" not in call_args


def test_login_success_logs_correctly():
    """Test that login_success logs the correct format."""
    with patch.object(security_log.logger, "info") as mock_info:
        security_log.login_success(ip="192.168.1.100", user_id="user-123", method="passkey")

        # Verify the log call
        mock_info.assert_called_once()
        call_args = mock_info.call_args[0][0]

        # Should contain LOGIN_SUCCESS, IP, user ID, and method
        assert "LOGIN_SUCCESS]" in call_args
        assert "ip=192.168.1.100" in call_args
        assert "user_id=user-123" in call_args
        assert "method=passkey" in call_args


def test_login_success_default_method():
    """Test that login_success uses default method when not specified."""
    with patch.object(security_log.logger, "info") as mock_info:
        security_log.login_success(ip="192.168.1.100", user_id="user-123")

        call_args = mock_info.call_args[0][0]
        assert "method=password" in call_args


def test_login_success_sanitizes_inputs():
    """Test that login_success sanitizes all inputs."""
    with patch.object(security_log.logger, "info") as mock_info:
        security_log.login_success(ip="192.168.1.100\n", user_id="user-123\r\n", method="passkey\0")

        call_args = mock_info.call_args[0][0]
        # Should not contain any control characters
        assert "\n" not in call_args
        assert "\r" not in call_args
        assert "\0" not in call_args
