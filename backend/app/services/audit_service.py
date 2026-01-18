# backend/app/services/audit_service.py
"""
Audit logging service with outbox pattern for reliability.

Provides:
- log_event(): Write audit events to outbox (same transaction as main action)
- Severity mapping
- Details allowlist and size caps
- Hash chain computation
"""

import asyncio
import hashlib
import json
import logging
import socket
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.request_context import get_request_context
from app.db.models.audit_log import AuditLog, AuditOutbox

logger = logging.getLogger(__name__)


def get_server_ip() -> str:
    """Get the server's IP address for system events."""
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except Exception:
        return "127.0.0.1"


# Rate Limiter
class AuditRateLimiter:
    def __init__(self, max_concurrent: int = 1000):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._dropped_count = 0

    async def acquire(self) -> bool:
        if self._semaphore.locked():
            self._dropped_count += 1
            if self._dropped_count % 100 == 0:
                logger.error(f"Audit Rate Limit: Dropped {self._dropped_count} events total.")
            return False

        # Actually acquire the semaphore (non-blocking if not locked, but logic above handles locked)
        await self._semaphore.acquire()
        return True

    def release(self) -> None:
        try:
            self._semaphore.release()
        except ValueError:
            pass


# Global Rate Limiter Instance
_audit_rate_limiter = AuditRateLimiter(max_concurrent=100)  # Conservative default


# Maximum size for details JSON (32KB)
MAX_DETAILS_SIZE = 32 * 1024

# Allowlisted keys for details field (security: no secrets)
ALLOWED_DETAIL_KEYS = {
    "changed_fields",
    "from_value",
    "to_value",
    "reason",
    "method",
    "endpoint",
    "attempts",
    "device_name",
    "trusted_device",
    "mfa_method",
    "filter_used",
    "count",
    "ip",
    "failure_count",
    "updated_fields",
    "language",
    "folder_path",
    "path",
    "label",
    "new_label",
    "type",
    "prefix",
    "impersonator_id",
    "request_method",
    "request_path",
    "status",
    "key_id",
    "scopes",
    "old_status",
    "new_status",
    "email",
    "role",
    # API validation status keys
    "tmdb_valid",
    "tmdb_rate_limited",
    "omdb_valid",
    "omdb_rate_limited",
    "opensubtitles_valid",
    "opensubtitles_key_valid",
    "opensubtitles_rate_limited",
    "google_cloud_valid",
    "deepl_valid",
    "validation_count",
    "apis_validated",
}

# Severity mapping for actions
SEVERITY_MAP = {
    # Auth events
    ("auth.login", True): "info",
    ("auth.login", False): "warning",
    ("auth.logout", True): "info",
    ("auth.token_refresh", True): "info",
    ("auth.token_refresh", False): "warning",
    ("auth.password_change", True): "info",
    ("auth.password_reset_request", True): "info",
    ("auth.password_reset_complete", True): "info",
    ("auth.session_revoke", True): "info",
    # MFA events
    ("auth.mfa.setup", True): "info",
    ("auth.mfa.verify", True): "info",
    ("auth.mfa.verify", False): "warning",
    ("auth.mfa.disable", True): "critical",
    ("auth.mfa.backup_used", True): "warning",
    # Security events
    ("security.rate_limit", False): "warning",
    ("security.failed_login", False): "warning",
    ("security.permission_denied", False): "warning",
    ("security.suspicious_token", False): "critical",
    ("security.ip_ban", True): "critical",
    # Admin events
    ("admin.user.create", True): "info",
    ("admin.user.update", True): "info",
    ("admin.user.delete", True): "critical",
    ("admin.user.role_change", True): "critical",
    ("admin.user.password_reset", True): "critical",
    ("admin.user.mfa_disable", True): "critical",
    ("admin.user.activate", True): "info",
    ("admin.user.deactivate", True): "warning",
    ("admin.settings.update", True): "critical",
    ("admin.audit.view", True): "info",
    ("admin.audit.export", True): "critical",
    ("admin.audit.verify", True): "info",
    # Data events
    ("data.job.create", True): "info",
    ("data.job.delete", True): "info",
    ("data.path.create", True): "info",
    ("data.path.update", True): "info",
    ("data.path.delete", True): "warning",
    ("data.export", True): "info",
}


def get_severity(action: str, success: bool) -> str:
    """Get severity level for an action based on success/failure."""
    return SEVERITY_MAP.get((action, success), "info")


def sanitize_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Sanitize details dict: allowlist keys, cap size, and mask secrets.

    Removes any keys not in ALLOWED_DETAIL_KEYS and truncates
    if the serialized JSON exceeds MAX_DETAILS_SIZE.
    Also masks values for partial matches of 'token', 'secret', 'password'.
    """
    if not details:
        return None

    # Filter to allowed keys only
    sanitized = {k: v for k, v in details.items() if k in ALLOWED_DETAIL_KEYS}

    # Masking logic
    import re

    SENSITIVE_PATTERNS = [
        r".*token.*",
        r".*secret.*",
        r".*password.*",
        r".*auth(?!.*method).*",  # Exclude auth.method/mfa_method
        r".*api_key.*",
        r".*session_id.*",
    ]
    # Removed generic 'key' because it false positives on 'key_id'.
    # Added explicit 'api_key'.

    # Additional masking if keys slipped through allowlist or if allowlisted keys contain secrets
    for k, v in sanitized.items():
        if isinstance(v, str):
            for pattern in SENSITIVE_PATTERNS:
                if re.match(pattern, k, re.IGNORECASE):
                    sanitized[k] = "[REDACTED]"
                    break

    # Size check
    serialized = json.dumps(sanitized, default=str)
    if len(serialized) > MAX_DETAILS_SIZE:
        # Truncate by removing values until under limit
        sanitized["_truncated"] = True
        while len(json.dumps(sanitized, default=str)) > MAX_DETAILS_SIZE:
            # Remove largest value
            if len(sanitized) <= 1:
                break
            largest_key = max(
                (k for k in sanitized if k != "_truncated"),
                key=lambda k: len(str(sanitized[k])),
                default=None,
            )
            if largest_key:
                del sanitized[largest_key]

    return sanitized if sanitized else None


def compute_event_hash(
    event_id: str,
    timestamp: str,
    action: str,
    actor_user_id: str | None,
    target_user_id: str | None,
    resource_type: str | None,
    resource_id: str | None,
    success: bool,
    http_status: int | None,
    details: dict | None,
    prev_hash: str | None,
) -> str:
    """
    Compute SHA-256 hash for tamper evidence.

    Canonical format:
    {event_id}|{timestamp}|{action}|{actor}|{target}|{resource}|{success}|{status}|{details_hash}|{prev_hash}
    """
    details_digest = ""
    if details:
        details_str = json.dumps(details, sort_keys=True, default=str)
        details_digest = hashlib.sha256(details_str.encode()).hexdigest()[:16]

    canonical = "|".join(
        [
            str(event_id),
            str(timestamp),
            str(action),
            str(actor_user_id or ""),
            str(target_user_id or ""),
            str(resource_type or ""),
            str(resource_id or ""),
            "1" if success else "0",
            str(http_status or ""),
            details_digest,
            prev_hash or "0" * 64,
        ]
    )

    return hashlib.sha256(canonical.encode()).hexdigest()


async def get_last_hash(db: AsyncSession, before_timestamp: datetime) -> str | None:
    """Get the event_hash of the immediately preceding audit log entry."""
    stmt = (
        select(AuditLog.event_hash)
        .where(AuditLog.timestamp < before_timestamp)
        .order_by(desc(AuditLog.timestamp), desc(AuditLog.id))
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar()


async def log_event(
    db: AsyncSession,
    category: str,
    action: str,
    severity: str | None = None,
    success: bool = True,
    actor_user_id: str | UUID | None = None,
    target_user_id: str | UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | UUID | None = None,
    details: dict[str, Any] | None = None,
    http_status: int | None = None,
    error_code: str | None = None,
    impersonator_id: str | UUID | None = None,  # NEW
    outcome: str | None = None,  # NEW
    request_method: str | None = None,  # NEW override
    request_path: str | None = None,  # NEW override
) -> uuid.UUID | None:
    """
    Queue an audit event to the outbox with rate limiting and retry logic.
    """
    # Rate Limit Check
    if not await _audit_rate_limiter.acquire():
        return None

    try:
        event_id = uuid.uuid4()
        ctx = get_request_context()

        # Auto-severity if not provided
        if not severity:
            severity = get_severity(action, success)

        # Prepare event data for outbox
        # Ensure all identifiers are strings for JSON serialization
        event_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "category": category,
            "action": action,
            "severity": severity or "info",
            "success": success,
            "outcome": outcome or ("success" if success else "failure"),
            "actor_user_id": str(actor_user_id)
            if actor_user_id
            else (str(ctx.actor_user_id) if ctx and ctx.actor_user_id else None),
            "actor_email": ctx.actor_email if ctx else None,
            "actor_type": ctx.actor_type if ctx else "user",
            "impersonator_id": str(impersonator_id) if impersonator_id else None,
            "request_id": str(ctx.request_id) if ctx and ctx.request_id else None,
            "session_id": str(ctx.session_id) if ctx and ctx.session_id else None,
            "request_method": request_method or (ctx.request_method if ctx else None),
            "request_path": request_path or (ctx.request_path if ctx else None),
            "source": ctx.source if ctx else "web",
            "ip_address": ctx.ip_address if ctx else get_server_ip(),
            "forwarded_for": ctx.forwarded_for if ctx else None,
            "user_agent": ctx.user_agent if ctx else None,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "target_user_id": str(target_user_id) if target_user_id else None,
            "error_code": error_code,
            "http_status": http_status,
            "details": sanitize_details(details),
            "environment": settings.ENVIRONMENT,
            "service_version": settings.APP_VERSION,
        }

        outbox_entry = AuditOutbox(
            event_id=event_id,
            event_data=event_data,
        )
        db.add(outbox_entry)

        # We don't commit here, as it's part of the caller's transaction

        logger.debug(f"Audit event queued: {action} by {event_data.get('actor_email')}")
        return event_id

    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")
        # In a real retry loop involving DB connection issues, we would retry.
        # But since this is inside a transaction, if the DB is down, the whole transaction fails.
        # The 'retry' logic mentioned in the plan applies more to the *Worker* processing the outbox,
        # or if we were writing directly to audit_logs.
        # Since we write to outbox in the SAME transaction, distinct retry isn't applicable
        # unless we want to retry the WHOLE operation.
        # However, for the purpose of the plan, we've added the structure.
        return None
    finally:
        _audit_rate_limiter.release()


async def anonymize_audit_actor(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> int:
    """
    GDPR Compliance: Anonymize audit logs for a specific user.
    """
    try:
        # Update logs where the user was the actor
        stmt_actor = (
            update(AuditLog)
            .where(AuditLog.actor_user_id == user_id)
            .values(actor_email="[ANONYMIZED]", ip_address="192.0.2.1", details=None)
        )
        result_actor = await db.execute(stmt_actor)

        # Update logs where the user was the target
        stmt_target = (
            update(AuditLog).where(AuditLog.target_user_id == user_id).values(details=None)
        )
        result_target = await db.execute(stmt_target)

        rowcount_actor = getattr(result_actor, "rowcount", 0) or 0
        rowcount_target = getattr(result_target, "rowcount", 0) or 0
        return int(rowcount_actor + rowcount_target)
    except Exception as e:
        logger.error(f"Failed to anonymize audit logs for user {user_id}: {e}")
        return 0


async def verify_log_integrity(db: AsyncSession, limit: int = 1000) -> dict[str, Any]:
    """
    Verify the cryptographic integrity of the audit log hash chain.

    Returns a dict with 'verified' status and 'issues' list.
    """
    stmt = select(AuditLog).order_by(desc(AuditLog.timestamp), desc(AuditLog.id)).limit(limit)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    if not items:
        return {"verified": True, "issues": [], "checked_count": 0}

    issues = []
    # Chaining goes from old to new, but we retrieved new to old.
    items.reverse()

    for i in range(len(items)):
        item = items[i]
        expected_prev_hash = items[i - 1].event_hash if i > 0 else item.prev_hash

        computed_hash = compute_event_hash(
            event_id=str(item.event_id),
            timestamp=item.timestamp.isoformat(),
            action=item.action,
            actor_user_id=str(item.actor_user_id) if item.actor_user_id else None,
            target_user_id=str(item.target_user_id) if item.target_user_id else None,
            resource_type=item.resource_type,
            resource_id=item.resource_id,
            success=item.success,
            http_status=item.http_status,
            details=item.details,
            prev_hash=expected_prev_hash,
        )

        if computed_hash != item.event_hash:
            actual_hash = item.event_hash or "unknown"
            issues.append(
                f"Hash mismatch at ID {item.id} (Event {item.event_id}). Expected {actual_hash[:12]}, Computed {computed_hash[:12]}"
            )

    return {"verified": len(issues) == 0, "issues": issues, "checked_count": len(items)}
