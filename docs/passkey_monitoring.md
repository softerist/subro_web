# Passkey Monitoring & Analytics

## SQL Queries for Monitoring

### Registration Success Rate (Last 24 Hours)

```sql
-- PostgreSQL
SELECT
  COUNT(*) FILTER (WHERE status = 'success') * 100.0 /
  NULLIF(COUNT(*), 0) as success_rate_percent,
  COUNT(*) FILTER (WHERE status = 'success') as successful_registrations,
  COUNT(*) FILTER (WHERE status = 'failure') as failed_registrations,
  COUNT(*) as total_attempts
FROM audit_logs
WHERE action = 'passkey.register'
  AND created_at > NOW() - INTERVAL '24 hours';
```

### Login Success Rate (Last 24 Hours)

```sql
SELECT
  COUNT(*) FILTER (WHERE status = 'success') * 100.0 /
  NULLIF(COUNT(*), 0) as success_rate_percent,
  COUNT(*) FILTER (WHERE status = 'success') as successful_logins,
  COUNT(*) FILTER (WHERE status = 'failure') as failed_logins
FROM audit_logs
WHERE action = 'passkey.login'
  AND created_at > NOW() - INTERVAL '24 hours';
```

### Top Errors (Last 24 Hours)

```sql
SELECT
  metadata->>'error_type' as error_type,
  COUNT(*) as error_count,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
FROM audit_logs
WHERE status = 'failure'
  AND action LIKE 'passkey.%'
  AND created_at > NOW() - INTERVAL '24 hours'
  AND metadata->>'error_type' IS NOT NULL
GROUP BY metadata->>'error_type'
ORDER BY error_count DESC
LIMIT 10;
```

### Passkey Adoption Metrics

```sql
-- Users with at least one passkey
SELECT
  COUNT(DISTINCT user_id) as users_with_passkeys,
  (SELECT COUNT(*) FROM users WHERE is_active = true) as total_active_users,
  COUNT(DISTINCT user_id) * 100.0 /
    (SELECT COUNT(*) FROM users WHERE is_active = true) as adoption_percentage
FROM passkeys
WHERE user_id IS NOT NULL;
```

### Passkey Login vs Password Login Ratio (Last 7 Days)

```sql
SELECT
  action,
  COUNT(*) as login_count,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as percentage
FROM audit_logs
WHERE action IN ('passkey.login', 'password.login')
  AND status = 'success'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY action;
```

### Deletion Activity (Last 7 Days)

```sql
SELECT
  DATE(created_at) as date,
  COUNT(*) as deletions
FROM audit_logs
WHERE action = 'passkey.delete'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

## Alert Thresholds

### Critical Alerts (🚨)

- **Registration Success Rate < 70%** — Indicates serious configuration or compatibility issues
- **Origin/RP ID Mismatch > 5** in last hour — Configuration regression
- **Complete Service Outage** — No successful operations in 15 minutes

### Warning Alerts (⚠️)

- **Registration Success Rate < 85%** — Below target, investigate
- **Login Success Rate < 90%** — Users having auth trouble
- **Deletion Spike** — >3x normal daily average without corresponding registrations

### Info Monitoring (ℹ️)

- **Adoption Rate** — Track percentage of users with at least one passkey
- **Login Method Preference** — Passkey vs password login ratio
- **Common Error Types** — Top 5 error types in last 24h

## Grafana Dashboard Panels (Optional)

### Panel 1: Success Rates

- **Type**: Stat
- **Query**: Registration & Login Success Rates
- **Thresholds**: Red <70%, Yellow <85%, Green ≥85%

### Panel 2: Error Distribution

- **Type**: Pie Chart
- **Query**: Top Errors
- **Update**: Every 5 minutes

### Panel 3: Adoption Trend

- **Type**: Time Series
- **Query**: Daily new passkey registrations
- **Time Range**: Last 30 days

### Panel 4: Login Methods

- **Type**: Bar Gauge
- **Query**: Passkey vs Password logins
- **Time Range**: Last 7 days

## Log Event Structure

All passkey operations should be logged to `audit_logs` table with:

```python
{
  "action": "passkey.register" | "passkey.login" | "passkey.delete" | "passkey.rename",
  "status": "success" | "failure",
  "user_id": "uuid",
  "metadata": {
    "error_type": "NotAllowedError" | "challenge_expired" | etc.,
    "device_info": "macOS – Chrome",
    "passkey_id": "credential-id" (for rename/delete),
    ...
  },
  "created_at": "timestamp"
}
```

## Implementation Checklist

- [ ] Add monitoring queries to observability platform
- [ ] Set up alert rules with thresholds above
- [ ] Create Grafana dashboard (if using)
- [ ] Document on-call playbook for common issues
- [ ] Schedule weekly review of metrics
