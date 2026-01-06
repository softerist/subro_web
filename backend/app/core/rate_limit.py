# backend/app/core/rate_limit.py
"""
Rate limiting configuration with trusted proxy handling.

Ensures we extract the REAL client IP address, not proxy IPs,
which is critical for fail2ban to ban the actual attacker.
"""

import ipaddress
import logging

from slowapi import Limiter
from starlette.requests import Request

logger = logging.getLogger(__name__)

API_KEY_PREFIX_LEN = 8


def _sanitize_for_log(value: str) -> str:
    """Sanitize user input for safe logging (prevent log injection)."""
    if not value:
        return ""
    # Remove newlines and carriage returns that could forge log entries
    return value.replace("\n", "[NL]").replace("\r", "[CR]").replace("\x00", "[NULL]")


# Trusted proxy networks (Docker internal, localhost, common private ranges)
# These are the IPs that we trust to provide accurate X-Forwarded-For headers
TRUSTED_PROXY_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # Localhost
    ipaddress.ip_network("10.0.0.0/8"),  # Docker/Private
    ipaddress.ip_network("172.16.0.0/12"),  # Docker default
    ipaddress.ip_network("192.168.0.0/16"),  # Private networks
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
]


def _is_trusted_proxy(ip: str) -> bool:
    """
    Check if an IP address is from a trusted proxy.

    Args:
        ip: IP address string to check

    Returns:
        True if the IP is in our trusted proxy list
    """
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in network for network in TRUSTED_PROXY_NETWORKS)
    except ValueError:
        # Invalid IP address format
        return False


def get_real_client_ip(request: Request) -> str:
    """
    Extract the real client IP address from the request.

    Only trusts X-Forwarded-For headers if the immediate connection
    comes from a trusted proxy. This prevents IP spoofing attacks.

    Args:
        request: Starlette request object

    Returns:
        The real client IP address
    """
    # Get the immediate connection IP
    client_ip = request.client.host if request.client else "unknown"

    if client_ip == "unknown":
        return client_ip

    # Only trust forwarded headers if the request came from a trusted proxy
    if _is_trusted_proxy(client_ip):
        # Check X-Forwarded-For header (standard proxy header)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For format: "client, proxy1, proxy2, ..."
            # The leftmost IP is the original client
            real_ip = forwarded_for.split(",")[0].strip()

            # Validate it looks like an IP
            try:
                ipaddress.ip_address(real_ip)
                return real_ip
            except ValueError:
                logger.warning("Invalid IP in X-Forwarded-For: %s", _sanitize_for_log(real_ip))
                return client_ip

        # Check X-Real-IP header (Nginx convention)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            try:
                ipaddress.ip_address(real_ip)
                return real_ip
            except ValueError:
                logger.warning("Invalid X-Real-IP: %s", _sanitize_for_log(real_ip))
                return client_ip

    # Not from a trusted proxy or no forwarded headers - use direct connection IP
    return client_ip


# Initialize the Limiter with our trusted proxy-aware IP extraction
limiter = Limiter(key_func=get_real_client_ip)


def get_api_key_or_ip(request: Request) -> str:
    """
    Get a rate limit key based on API key (if present) or client IP.

    This allows API key-based rate limiting separate from IP-based.

    Args:
        request: Starlette request object

    Returns:
        Rate limit key string
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"api_key:{api_key[:API_KEY_PREFIX_LEN]}"
    return get_real_client_ip(request)
