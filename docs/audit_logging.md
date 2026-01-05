# Audit Logging Developer Guide

This document explains how to instrument new events for the audit logging system.

## Core Concepts

The audit system uses an **Outbox Pattern** to ensure reliability.

- `log_event()` writes to the `audit_outbox` table within the same database transaction.
- A background worker processes the outbox, computes hash chains, and moves entries to the `audit_logs` table.

## Instrumenting an Event

To log a new event, use the `app.services.audit_service.log_event` function:

```python
from app.services import audit_service

await audit_service.log_event(
    db,                             # AsyncSession
    category="security",            # e.g., auth, security, data, admin
    action="security.api_key_used", # Pattern: category.action
    severity="info",                # info | warning | error | critical (auto-set if omitted)
    success=True,
    actor_user_id=user.id,          # Optional: defaults to current requester
    target_user_id=target_id,       # Optional: who was affected
    resource_type="api_key",        # Optional: what was affected
    resource_id=key_id,
    details={                       # Key-value pairs for additional context
        "prefix": "sk-...",
        "method": "API"
    }
)
```

## Security & Sanitization

The `details` field is automatically sanitized:

1. **Allowlist**: Only keys in `ALLOWED_DETAIL_KEYS` are preserved.
2. **PII Masking**: Values matching sensitive patterns (e.g., token, secret, password) are redacted.
3. **Size Limit**: Objects exceeding 32KB are truncated safely to prevent DB bloat.

## Best Practices

- **Action Names**: Use namespaced actions (e.g., `auth.mfa_enabled`).
- **Severity**: Use `critical` for actions that reduce security (e.g., disabling MFA).
- **Outcome**: For failures, provide a `reason_code` to help support/security analysis.
- **Transactions**: Always ensure you commit the transaction if you call `log_event` outside of an existing request/response cycle.
