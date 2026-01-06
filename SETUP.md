# 🚀 Setup Guide

## Prerequisites

- Docker & Docker Compose installed
- Git

---

## Quick Start

### 1. Create Environment File

The application **requires** a `.env` file to run. Copy the example and configure it:

```bash
cd /home/user/subro_web
cp .env.example .env
```

### 2. Configure Critical Variables

Edit `.env` and **change all `CHANGE_ME_*` values**. At minimum, set:

```bash
# Security (REQUIRED - generate with: openssl rand -hex 32)
JWT_SECRET_KEY=your_generated_secret_here
JWT_REFRESH_SECRET_KEY=your_generated_secret_here
API_KEY_PEPPER=your_generated_secret_here
DATA_ENCRYPTION_KEYS=your_generated_secret_here

# Database (REQUIRED)
POSTGRES_PASSWORD=your_secure_database_password

# Initial Admin User (REQUIRED)
FIRST_SUPERUSER_EMAIL=admin@example.com
FIRST_SUPERUSER_PASSWORD=your_secure_admin_password

# Test Database (for testing)
DB_TEST_PASSWORD=your_test_database_password
```

**💡 Generate secure secrets:**

```bash
# Generate a 32-byte hex secret
openssl rand -hex 32
```

### 3. Adjust Paths (if needed)

Update these in `.env` to match your system:

```bash
# Docker Host Settings
HOST_MEDIA_PATH=/mnt/usb/Media/Movies
HOST_DOWNLOADS_PATH=/root/Downloads
```

### 4. Start the Stack

```bash
cd infra/docker
docker compose --env-file ../../.env \
               -f docker-compose.yml \
               -f docker-compose.override.yml \
               up -d
```

> **Note:** The `--env-file ../../.env` flag is required because Docker Compose doesn't auto-load `.env` from parent directories.

---

## Validation

### Verify Configuration Syntax

```bash
# This should NOT show "invalid proto:" error
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/docker-compose.override.yml \
               config --quiet
```

**Expected**: No errors (warnings about .env are OK **before** creating `.env`, but gone after)

### Check Services

```bash
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/docker-compose.override.yml \
               ps
```

All services should show as "healthy" or "running".

---

## Understanding Environment Variables

### Where Variables Come From

Your Docker Compose setup reads variables in this order:

1. **`.env` file** (root directory) - Main configuration
2. **`backend/.env.test`** - Test-specific overrides
3. **Shell environment** - Overrides everything

### Docker Compose Files

- **`docker-compose.yml`**: Base configuration (requires `.env`)
- **`docker-compose.override.yml`**: Development overrides (has sensible defaults)

#### Why No Inline Defaults in docker-compose.yml?

We follow the **standard Docker Compose pattern**:

✅ **Clean YAML files** - Easy to read and maintain
✅ **Single source of truth** - All defaults in `.env.example`
✅ **Explicit configuration** - Prevents accidental misconfiguration
✅ **Better errors** - Missing `.env` shows clear warnings

---

## Common Issues

### ❌ "invalid proto:" Error

**Cause**: No `.env` file exists

**Fix**:

```bash
cp .env.example .env
# Then edit .env with your values
```

### ❌ "WARN: The 'VARIABLE' is not set"

**Cause**: Variable missing from `.env`

**Fix**: Check `.env.example` for the required variable and add it to `.env`

### ❌ Services Fail to Start

**Cause**: Invalid credentials or missing required secrets

**Fix**: Ensure all `CHANGE_ME_*` values in `.env` are replaced with real values

---

## For Developers

### Testing Configuration

```bash
# Validate backend configuration
cd backend
python -m app.core.config

# Run tests
pytest

# Verify infrastructure
python debug_scripts/verify_infrastructure.py
```

### Environment Files Summary

| File                        | Purpose                  | Committed           |
| --------------------------- | ------------------------ | ------------------- |
| `.env.example`              | Template with defaults   | ✅ Yes              |
| `.env`                      | Your local configuration | ❌ No (.gitignored) |
| `.env.prod.example`         | Production template      | ✅ Yes              |
| `backend/.env.test`         | Test configuration       | ✅ Yes              |
| `backend/.env.test.example` | Test template            | ✅ Yes              |

---

## Next Steps

1. ✅ Created `.env` from `.env.example`
2. ✅ Changed all secrets
3. ✅ Started services successfully
4. 📚 Read the [API Documentation](http://localhost:8001/api/v1/docs)
5. 🎯 Visit the [Frontend](http://localhost:8090)

---

## Need Help?

- Check [code_review.md](.gemini/antigravity/brain/f3d9d8ba-1397-42cf-b50f-f6a8976c717e/code_review.md) for detailed configuration review
- See [.env.example](.env.example) for all available options
- Review [backend/.env.test](backend/.env.test) for test setup examples
