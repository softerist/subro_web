# backend/app/core/request_context.py
"""
Request context middleware for audit logging.

Attaches per-request context (request_id, actor, IP, user_agent, source)
that the audit service auto-attaches to all events.
"""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.rate_limit import get_real_client_ip


@dataclass
class RequestContext:
    """Context attached to each request for audit logging."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    ip_address: str = "unknown"
    forwarded_for: str | None = None
    user_agent: str | None = None
    source: str = "web"  # web | api | cli | system
    session_id: str | None = None

    # NEW: Request details
    request_method: str | None = None
    request_path: str | None = None

    # Actor info (set after authentication)
    actor_user_id: str | None = None
    actor_email: str | None = None
    actor_type: str = "user"  # user | system | api_key


# Context variable for request-scoped data
_request_context: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def get_request_context() -> RequestContext | None:
    """Get the current request context."""
    return _request_context.get()


def set_request_context(ctx: RequestContext) -> None:
    """Set the current request context."""
    _request_context.set(ctx)


def set_actor(
    user_id: str | None = None,
    email: str | None = None,
    actor_type: str = "user",
) -> None:
    """Set actor information in the current request context."""
    ctx = get_request_context()
    if ctx:
        ctx.actor_user_id = user_id
        ctx.actor_email = email
        ctx.actor_type = actor_type


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that creates and attaches request context.

    Must be added early in the middleware stack.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Determine source based on path or headers
        source = "web"
        if request.url.path.startswith("/api/"):
            source = "api"
        if request.headers.get("X-CLI-Client"):
            source = "cli"

        # Extract IP with trusted proxy handling
        ip_address = get_real_client_ip(request)
        forwarded_for = request.headers.get("X-Forwarded-For")

        # Truncate user agent to 512 chars
        user_agent = request.headers.get("User-Agent", "")
        if user_agent and len(user_agent) > 512:
            user_agent = user_agent[:509] + "..."

        # Create context
        ctx = RequestContext(
            ip_address=ip_address,
            forwarded_for=forwarded_for,
            user_agent=user_agent or None,
            source=source,
            request_method=request.method,
            request_path=request.url.path[:255],  # Truncate to fit column
        )

        # Set context for this request
        set_request_context(ctx)

        # Add request_id to response headers for tracing
        token = _request_context.set(ctx)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = ctx.request_id
            return response
        finally:
            _request_context.reset(token)
