# Audit Log Operational Guide

This document covers administrative operations for the audit logging system.

## Integrity Verification

Audit logs are cryptographically chained using SHA-256 hashes. If any row or sequence is altered, the chain will break.

### Verifying via UI

1. Navigate to **Admin > Audit Log**.
2. Click **Scan Integrity**.
3. The system will scan the last 1000 events and report any mismatches.

### Verifying via CLI

You can run the verification script directly on the server:

```bash
python -m app.scripts.verify_audit_integrity
```

## Log Exporting

For compliance audits, logs can be exported in JSONL format.

1. Use the **Filters** to narrow down the desired time range or actor.
2. Click **Export Logs**.
3. The export will process in the background. Once complete, a download link will appear.

## Log Retention and Partitioning

Logs are stored in monthly partitions (e.g., `audit_logs_2024_01`).

### Archiving Old Logs

To archive logs older than 1 year:

1. Identify the partition: `audit_logs_2023_01`.
2. Detach the partition:
   ```sql
   ALTER TABLE audit_logs DETACH PARTITION audit_logs_2023_01;
   ```
3. Export the detached table to cold storage and drop it from the database.

## GDPR Compliance (Right to Erasure)

When a user requests data deletion, audit logs must be anonymized rather than deleted (to maintain the integrity of the chain).

Use the following service function:

```python
from app.services.audit_service import anonymize_audit_actor
await anonymize_audit_actor(db, user_id)
```

This will replace the actor email with `[ANONYMIZED]` and scrub IP addresses for that user.
