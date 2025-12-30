# Deployment Guide

This guide describes how to deploy the application to a production environment using Docker Compose with Blue/Green deployment capabilities and automated backups.

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
   cp infra/prod.env.example .env.prod
   ```

   Edit `.env.prod` and set secure values:

   ```bash
   nano .env.prod
   ```

   > [!IMPORTANT]
   > Ensure `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, `API_KEY_PEPPER`, `POSTGRES_PASSWORD`, `FIRST_SUPERUSER_PASSWORD`, and `SETUP_TOKEN` are strong and unique.
   >
   > When completing the setup wizard in production, include the `X-Setup-Token` header with the value of `SETUP_TOKEN`.

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

## Setup Wizard (Production)

In production, setup endpoints require the `X-Setup-Token` header.

UI flow:

- Open `/setup` in the browser.
- Enter the setup token from `.env.prod` (SETUP_TOKEN) in the Setup Token field.

CLI flow:

```bash
curl -X POST https://your-domain/api/v1/setup/complete \
  -H "Content-Type: application/json" \
  -H "X-Setup-Token: YOUR_SETUP_TOKEN" \
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
