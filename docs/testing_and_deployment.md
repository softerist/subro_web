# Testing and Deployment Plan

## 1. Overview

This document checks the verification strategy for the new Audit Log features across Development and Production environments.

## 2. Test Suite Composition

### Backend Tests

We have added specific test suites for audit logging:

- **Unit Tests**: `backend/tests/unit/test_audit_security_unit.py` (Rate Limit, Sanitization, GDPR)
- **Integration Tests**: `backend/tests/api/test_audit_integration.py` (API Keys, MFA, Tamper Detection)
- **API Tests**: `backend/tests/api/test_audit.py` (Pagination, Stats, Integrity)

### Frontend Tests (To Be Created)

- **Component Tests**: `frontend/src/features/admin/components/AuditLogTable.test.tsx`
- **Page Tests**: `frontend/src/features/admin/pages/AuditLogPage.test.tsx`

## 3. Execution Strategy

### Development Environment

Running tests locally during development.

**Backend:**

```bash
# Run all audit-related tests
make test-audit

# Run specific integration tests
docker compose -f infra/docker/docker-compose.yml exec api poetry run pytest backend/tests/api/test_audit_integration.py -v
```

**Frontend:**

```bash
# Run all frontend tests
make test-ts

# Run integration tests (requires dev stack up)
make test-integration
```

### Production Environment

Verifying features after deployment to the "Blue/Green" production stack.

**Backend Integration:**
This command copies the test suite into the running production container (`blue-api-1`) and executes it against the live production database (safe tests only).

```bash
make test-integration-prod
```

> **Warning**: Ensure `test_audit_integration.py` does not perform destructive actions on critical data. Our tests use dedicated test users/tenants.

## 4. Manual Verification Steps

1. **Integrity Check**:
   - Go to `/admin/audit`.
   - Click "Verify Integrity".
   - Confirm "Valid Signature".

2. **RLS Enforcement**:
   - SSH into the database: `docker exec -it subapp_prod_db psql -U appuser -d subappdb`
   - Attempt validation: `DELETE FROM audit_logs WHERE action='auth.login';`
   - Expect: `DELETE 0` (Policy violation).

## 5. Deployment Plan

1. **Deploy to Prod**:

   ```bash
   make prod
   ```

   This triggers the blue-green deployment script.

2. **Verify Deployment**:
   - Check logs: `make logs-api`
   - Run prod integration tests: `make test-integration-prod`
