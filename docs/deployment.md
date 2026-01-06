# Deployment Guide

This guide describes how to deploy the application to a production environment using Docker Compose with Blue/Green deployment capabilities and automated backups.

**Two deployment methods are supported:**

1. **Manual deployment** - SSH into the server and run deployment scripts manually
2. **CI/CD deployment** - Automated deployment via GitLab CI/CD pipeline

## Prerequisites

- **Docker Engine** (24.0+) & **Docker Compose Plugin** (2.20+)
- **Git**
- A Linux server (Ubuntu/Debian recommended)
- A domain name pointing to the server IP (for Caddy)

## 1. Initial Setup

1. **Clone the Repository**:

   ```bash
   git clone <your-repo-url> /opt/subro_web
   cd /opt/subro_web
   ```

2. **Configure Production Environment**:

   Copy the template to `.env.prod`:

   ```bash
   cp infra/.env.prod.example .env.prod
   ```

   Edit `.env.prod` and set secure values:

   ```bash
   nano .env.prod
   ```

   > [!IMPORTANT]
   > Ensure `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, `API_KEY_PEPPER`, `POSTGRES_PASSWORD`, `FIRST_SUPERUSER_PASSWORD`, and `ONBOARDING_TOKEN` are strong and unique.
   >
   > When completing the onboarding wizard in production, include the `X-Onboarding-Token` header with the value of `ONBOARDING_TOKEN`.

3. **Prepare Directory Structure**:
   Ensure directories for persistent data exist:

   ```bash
   # These usage Docker volumes, so explicit creation isn't usually needed,
   # but for backups or media mounts:
   mkdir -p /mnt/sata0/Media
   sudo chown 1000:1000 /mnt/sata0/Media # Assuming appuser UID 1000
   mkdir -p /backups
   ```

## 2. Infrastructure Startup

The infrastructure consists of three stacks:

- **Gateway**: Caddy (Load Balancer/Ingress).
- **Data**: PostgreSQL and Redis (Stateful).
- **App**: API, Worker, Frontend (Stateless, Blue/Green capable).

Run the initial deployment script which handles all of this:

```bash
chmod +x infra/scripts/blue_green_deploy.sh
./infra/scripts/blue_green_deploy.sh
```

## Onboarding Wizard (Production)

In production, onboarding endpoints require the `X-Onboarding-Token` header.

UI flow:

- Open `/onboarding` in the browser.
- Enter the onboarding token from `.env.prod` (ONBOARDING_TOKEN) in the Onboarding Token field.

CLI flow:

```bash
curl -X POST https://your-domain/api/v1/onboarding/complete \
  -H "Content-Type: application/json" \
  -H "X-Onboarding-Token: YOUR_ONBOARDING_TOKEN" \
  -d '{"admin_email":"admin@example.com","admin_password":"STRONG_PASSWORD"}'
```

This script will:

1. Launch/Verify Gateway and Data stacks (bootstrapping `infra` project).
2. Deploy the application stack (e.g., `blue` project).
3. Wait for health checks.
4. Configure Caddy to point to the new stack.

## 3. Routine Deployments (Updates)

To deploy a new version of the code:

1. **Pull changes**:

   ```bash
   git pull origin main
   ```

2. **Run Deployment Script**:

   ```bash
   ./infra/scripts/blue_green_deploy.sh
   ```

   **shortcuts:**
   - `make prod`: Runs the script with default settings (re-encrypts data).
   - `make prod-skip-reencrypt`: Runs with `REENCRYPT_ON_DEPLOY=0` (skips re-encryption, faster).

   The script automatically:
   - Identifies the _active_ color (e.g., Blue).
   - Builds and starts the _inactive_ color (e.g., Green).
   - Verifies health of the new stack.
   - Runs database migrations and re-encrypts encrypted fields if a key rotation is detected.
   - Updates Caddy traffic.
   - Stops the old stack.

   > [!NOTE]
   > Re-encryption runs automatically when `DATA_ENCRYPTION_KEYS` includes multiple entries (new key first, old keys after).
   > You can skip it with `REENCRYPT_ON_DEPLOY=0` or force it with `REENCRYPT_FORCE=1` when running the deploy script.
   > [!NOTE]
   > Zero downtime is achieved as Caddy waits for the new backend to be healthy before switching.

## 4. Post-Deploy Sanity Check

Use the sanity check script to validate health and basic job creation after a deployment:

```bash
# Uses infra/.env.prod by default (falls back to .env.prod)
infra/scripts/prod_sanity_check.sh

# Include a quick job creation test (requires an API key)
# Avoid putting secrets into shell history; prefer the read-from-stdin variant below.
SANITY_API_KEY=your_api_key infra/scripts/prod_sanity_check.sh
```

To get an API key:

- UI: go to Settings -> API Key -> Generate (the full key is shown once).
- API: call the user endpoint and store the `api_key` value.

```bash
curl -X POST https://your-domain/api/v1/users/me/api-key \
  -H "Authorization: Bearer <JWT>"
```

Safer shell usage (prevents history leaks):

```bash
read -s -p "SANITY_API_KEY: " SANITY_API_KEY && echo
SANITY_API_KEY="$SANITY_API_KEY" infra/scripts/prod_sanity_check.sh
unset SANITY_API_KEY
```

Notes:

- Treat the API key as a secret (avoid logs and process listings).
- Prefer a dedicated low-privilege user and rotate/revoke the key after checks.
- Use HTTPS and avoid `SANITY_INSECURE=1` in production.

## 5. Backups

Database backups are handled by the `backup` service in the Data stack.

### Manual Backup

To trigger an immediate backup:

```bash
docker compose -p infra -f infra/docker/compose.data.yml exec backup /usr/local/bin/backup.sh
```

### Scheduled Backup (Cron)

Add a cron job to the host to trigger daily backups (e.g., at 3 AM):

```bash
# crontab -e
0 3 * * * docker compose -p infra -f /opt/subro_web/infra/docker/compose.data.yml exec -T backup /usr/local/bin/backup.sh >> /var/log/subro_backup.log 2>&1
```

## 6. Troubleshooting

- **View Logs**:

  ```bash
  # Gateway (Caddy)
  docker compose -p infra -f infra/docker/compose.gateway.yml logs -f

  # App (Active Color)
  # Check which is active (blue or green)
  docker ps
  docker compose -p blue -f infra/docker/compose.prod.yml logs -f
  ```

- **Rollback (Manual)**:
  If a deployment fails _after_ switching traffic (rare, as script checks health first), you can manually switch Caddy back by editing `infra/docker/Caddyfile.prod` and reloading Caddy, or simply re-running the deploy script (it will try to deploy the other color again).

- **Database Access**:

  ```bash
  docker compose -p infra -f infra/docker/compose.data.yml exec db psql -U subapp_user subappdb
  ```

---

## 7. CI/CD Deployment (GitLab)

The project includes a GitLab CI/CD pipeline for automated deployment. This method builds images in CI, pushes to GitLab Container Registry, and deploys via SSH.

### 7.1. GitLab CI/CD Variables Setup

Configure these variables in **Settings → CI/CD → Variables**:

| Variable                | Scope         | Flags             | Value                                                         |
| ----------------------- | ------------- | ----------------- | ------------------------------------------------------------- |
| `REGISTRY_USER`         | production    | -                 | Your GitLab username or deploy token name                     |
| `REGISTRY_PASSWORD`     | production    | Masked            | GitLab personal access token or deploy token password         |
| `SSH_HOST`              | production    | Protected         | Production server hostname/IP                                 |
| `SSH_PORT`              | production    | Protected         | SSH port (default: 22)                                        |
| `SSH_USER`              | All (default) | -                 | SSH username for deployment (e.g., `deploy`)                  |
| `SSH_PRIVATE_KEY`       | production    | Protected, Masked | Base64-encoded private SSH key                                |
| `PROD_ENV_FILE`         | production    | Protected, Masked | Base64-encoded contents of `.env.prod`                        |
| `VITE_API_BASE_URL`     | production    | -                 | Frontend API URL (e.g., `https://your-domain.com/api/v1`)     |
| `VITE_WS_BASE_URL`      | production    | -                 | Frontend WebSocket URL (e.g., `wss://your-domain.com/api/v1`) |
| `VITE_ONBOARDING_TOKEN` | production    | Masked            | Onboarding token for initial configuration                    |

#### Generate SSH Key

```bash
# Generate SSH keypair for deployment
ssh-keygen -t ed25519 -C "gitlab-deploy@subro_web" -f ~/.ssh/gitlab_deploy

# Copy public key to production server
ssh-copy-id -i ~/.ssh/gitlab_deploy.pub your-user@your-server

# Base64 encode private key for GitLab variable
base64 -w0 < ~/.ssh/gitlab_deploy
# Copy output to SSH_PRIVATE_KEY variable
```

#### Base64 Encode .env.prod

```bash
# Encode your production environment file
base64 -w0 < .env.prod
# Copy output to PROD_ENV_FILE variable
```

#### Get SSH Host Key

```bash
# Get server's SSH host key for verification
ssh-keyscan -p 22 your-server.com
# Copy output to SSH_HOST_KEY variable (if you add this to the pipeline)
```

### 7.2. Pipeline Stages

The `.gitlab-ci.yml` pipeline includes:

1. **pre** - Debug information
2. **build** - Build Docker images for api, worker, frontend (parallel)
3. **test** - Run end-to-end container tests
4. **scan** - Security scanning (Trivy, Semgrep, secrets)
5. **deploy** - Manual deployment to production
6. **verify** - Post-deployment health check

### 7.3. Triggering a Deployment

1. **Push to `main` branch** - Automatically runs build, test, and scan stages
2. **Manual trigger** - Navigate to **CI/CD → Pipelines** → Select latest pipeline → Click manual "deploy_prod" job
3. **Wait for health check** - Manually trigger "verify_prod" after deployment

### 7.4. Deployment Process

When you trigger `deploy_prod`:

1. SSH connection established to production server
2. `.env.prod` decoded and written securely
3. Docker login to GitLab Container Registry
4. Image tags exported as environment variables
5. `blue_green_deploy.sh` executed with `USE_PREBUILT_IMAGES=1`
6. Images pulled from registry
7. New stack (blue/green) started
8. Health checks performed
9. Old worker stopped (prevents job duplication)
10. Database migrations run
11. Caddy traffic switched to new stack
12. Old stack stopped
13. Conservative image pruning (keeps 7 days)

### 7.5. Migration Strategy

> [!WARNING] > **Both blue and green stacks run simultaneously during cutover (~30-60 seconds)!**

#### Expand-then-Contract Pattern

All database schema changes **must** follow this pattern:

1. **Expand Phase** (Release N):
   - Add new columns/tables with defaults or nullable
   - Deploy new code that works with both old and new schema
   - Old code still works during migration period

2. **Contract Phase** (Release N+1):
   - Remove deprecated columns/tables
   - Clean up old code references

#### Migration Rules

- ✅ Add columns with `DEFAULT` or `NULLABLE`
- ✅ Add new tables
- ✅ Add indexes (use `CONCURRENTLY` in PostgreSQL)
- ❌ Rename columns (use expand-contract: add new, deprecate old)
- ❌ Drop columns (must wait for next release)
- ❌ Change column types (requires expand-contract)

#### Example: Renaming a Column

**Bad** (breaks during blue-green overlap):

```sql
ALTER TABLE users RENAME COLUMN name TO full_name;
```

**Good** (expand-then-contract):

Release 1:

```sql
-- Add new column
ALTER TABLE users ADD COLUMN full_name VARCHAR(255);
-- Copy data
UPDATE users SET full_name = name WHERE full_name IS NULL;
-- Code supports both "name" and "full_name"
```

Release 2:

```sql
-- Remove old column
ALTER TABLE users DROP COLUMN name;
-- Code only uses "full_name"
```

### 7.6. Rollback Procedures

#### Via GitLab CI

1. Navigate to **CI/CD → Pipelines**
2. Find the previous successful deployment
3. Click "Retry" on the `deploy_prod` job
4. Images are pulled by commit SHA (immutable)

#### Manual Rollback

If CI/CD is unavailable:

```bash
# SSH into production
ssh user@your-server

# Check which color is active
docker ps | grep -E "(blue|green)-api"

# If green is active, rollback to blue
cd /opt/subro_web
docker compose -p blue -f infra/docker/compose.prod.yml up -d

# Update Caddy to point to blue
# Edit infra/docker/Caddyfile.prod manually or run:
sed -i 's/green-api-1/blue-api-1/g; s/green-frontend-1/blue-frontend-1/g' infra/docker/Caddyfile.prod
docker compose -p infra -f infra/docker/compose.gateway.yml exec caddy caddy reload --config /etc/caddy/Caddyfile.prod

# Stop green
docker compose -p green -f infra/docker/compose.prod.yml down
```

### 7.7. Troubleshooting CI/CD

#### Build Failures

**Symptom**: Build job fails with "context deadline exceeded"

**Solution**:

- Increase Docker build timeout in Settings → CI/CD → General pipelines → Timeout
- Check if buildx cache is corrupted - clear cache by removing cache registry images

#### Registry Authentication Failures

**Symptom**: `Error response from daemon: unauthorized`

**Solution**:

- Verify `REGISTRY_USER` and `REGISTRY_PASSWORD` are correct
- For personal access token: ensure it has `read_registry` and `write_registry` scopes
- For deploy token: ensure it has `read_registry` scope

#### SSH Connection Failures

**Symptom**: `Permission denied (publickey)`

**Solution**:

- Verify `SSH_PRIVATE_KEY` is base64-encoded correctly
- Test SSH key manually: `echo "$SSH_PRIVATE_KEY" | base64 -d | ssh-add -`
- Ensure public key is in server's `~/.ssh/authorized_keys`

#### Health Check Timeouts

**Symptom**: Deployment aborts with "failed health check"

**Solution**:

- Check API logs: `docker logs blue-api-1` or `docker logs green-api-1`
- Common issues:
  - Database connection failure
  - Missing environment variables
  - Port conflicts
  - Migrations taking too long

#### Variable Size Limits

**Symptom**: `PROD_ENV_FILE` too large

**Solution**:

- GitLab variable limit: 64KB
- After base64 encoding, file expands ~33%
- Max original `.env.prod` size: ~48KB
- If exceeded, consider splitting secrets or using external secret manager

---

## 8. Security Considerations

### CI/CD Security Checklist

- ✅ All secrets are masked in GitLab variables
- ✅ Production variables are protected (only `main` branch)
- ✅ SSH host key verification via `ssh-keyscan`
- ✅ Container vulnerability scanning (Trivy)
- ✅ SAST scanning (Semgrep)
- ✅ Secret scanning in repository
- ✅ `resource_group` prevents concurrent deploys
- ✅ Conservative image pruning retains rollback capability

### Regular Maintenance

- **Rotate SSH keys** every 90 days
- **Rotate GitLab tokens** every 90 days
- **Review scan results** before deployment
- **Test rollback** procedure quarterly
- **Update base images** monthly for security patches
