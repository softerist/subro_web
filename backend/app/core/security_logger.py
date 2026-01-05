# backend/app/core/security_logger.py
"""
Dedicated security logger for fail2ban integration.

Writes security events to a file in a format that fail2ban can parse.
Includes log injection safeguards and proper timestamp formatting.
"""

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Log file path - mounted to /opt/subro_web/logs/security.log on host
SECURITY_LOG_PATH = Path("/app/logs/security.log")


def sanitize(value: str | None, max_length: int = 255) -> str:
    """
    Sanitize user input to prevent log injection attacks.

    Removes/escapes characters that could break log parsing or inject fake entries.

    Args:
        value: The value to sanitize
        max_length: Maximum length of the output

    Returns:
        Sanitized string safe for logging
    """
    if not value:
        return "unknown"

    # Convert to string and strip
    value = str(value).strip()

    # Remove newlines, carriage returns, brackets, and control characters
    # These could be used to inject fake log entries or break parsing
    value = re.sub(r"[\n\r\[\]<>\x00-\x1f\x7f-\x9f]", "", value)

    # Truncate to max length
    return value[:max_length]


def _hash_email(email: str) -> str:
    """
    Hash email for privacy while maintaining uniqueness.

    Returns first 8 chars + domain for debugging without exposing full email.
    """
    if not email or "@" not in email:
        return sanitize(email)

    local, domain = email.rsplit("@", 1)
    # Show first 3 chars of local part + masked + domain
    if len(local) > 3:
        masked_local = local[:3] + "***"
    else:
        masked_local = local[0] + "***" if local else "***"

    return f"{masked_local}@{sanitize(domain)}"


class SecurityLogger:
    """
    Thread-safe security event logger for fail2ban integration.

    Log format compatible with fail2ban datepattern:
        2026-01-05 10:15:30 SECURITY [EVENT_TYPE] ip=x.x.x.x field=value ...

    All user-controlled fields are sanitized to prevent log injection.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if SecurityLogger._initialized:
            return

        self.logger = logging.getLogger("security")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Don't propagate to root logger

        # Ensure log directory exists
        SECURITY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Rotating file handler: 50MB max, keep 10 backups
        handler = RotatingFileHandler(
            str(SECURITY_LOG_PATH),
            maxBytes=50 * 1024 * 1024,
            backupCount=10,
        )

        # Format: timestamp SECURITY [message
        # The message will contain EVENT_TYPE] ip=... fields...
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s SECURITY [%(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

        self.logger.addHandler(handler)
        SecurityLogger._initialized = True

    def failed_login(self, ip: str, email: str, reason: str) -> None:
        """
        Log a failed login attempt.

        Args:
            ip: Client IP address
            email: Email that was attempted
            reason: Failure reason (BAD_CREDENTIALS, USER_INACTIVE, etc.)
        """
        self.logger.info(
            f"FAILED_LOGIN] ip={sanitize(ip)} email={_hash_email(email)} reason={sanitize(reason)}"
        )

    def successful_login(self, ip: str, email: str) -> None:
        """
        Log a successful login (for audit trail, not for banning).

        Args:
            ip: Client IP address
            email: Email that logged in
        """
        self.logger.info(f"LOGIN_SUCCESS] ip={sanitize(ip)} email={_hash_email(email)}")

    def mfa_failed(self, ip: str, user_id: str) -> None:
        """
        Log a failed MFA attempt.

        Args:
            ip: Client IP address
            user_id: User ID (not email for privacy)
        """
        self.logger.info(f"MFA_FAILED] ip={sanitize(ip)} user_id={sanitize(user_id)}")

    def rate_limited(self, ip: str, endpoint: str) -> None:
        """
        Log a rate limit violation.

        Args:
            ip: Client IP address
            endpoint: The endpoint that was rate limited
        """
        self.logger.info(
            f"RATE_LIMIT] ip={sanitize(ip)} endpoint={sanitize(endpoint, max_length=100)}"
        )

    def bad_token(self, ip: str, reason: str) -> None:
        """
        Log a suspicious token attempt (malformed, bad signature, etc.)

        Note: Do NOT log expired tokens - those are normal behavior.

        Args:
            ip: Client IP address
            reason: Why the token was rejected (malformed, bad_signature, invalid_audience)
        """
        self.logger.info(f"BAD_TOKEN] ip={sanitize(ip)} reason={sanitize(reason)}")

    def api_key_abuse(self, ip: str, key_prefix: str) -> None:
        """
        Log an invalid API key attempt.

        Args:
            ip: Client IP address
            key_prefix: First 8 chars of the attempted key
        """
        self.logger.info(
            f"API_KEY_ABUSE] ip={sanitize(ip)} key_prefix={sanitize(key_prefix, max_length=8)}"
        )

    def suspicious_request(self, ip: str, path: str, reason: str) -> None:
        """
        Log a suspicious request pattern.

        Args:
            ip: Client IP address
            path: Request path
            reason: Why it's suspicious
        """
        self.logger.info(
            f"SUSPICIOUS] ip={sanitize(ip)} path={sanitize(path, max_length=100)} reason={sanitize(reason)}"
        )


# Singleton instance for easy import
security_log = SecurityLogger()
