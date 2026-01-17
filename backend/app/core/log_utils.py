# backend/app/core/log_utils.py
"""Utilities for safe logging to prevent log injection attacks."""


def sanitize_for_log(value: str) -> str:
    """Sanitize user-controlled strings for safe logging.

    Removes newlines and carriage returns to prevent log injection/forging.

    Usage:
        from app.core.log_utils import sanitize_for_log
        logger.info("User logged in: %s", sanitize_for_log(user.email))
    """
    if value is None:
        return ""
    return str(value).replace("\n", "").replace("\r", "")
