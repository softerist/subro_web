# Deployment Guide

This guide describes how to deploy the application to a production environment using Docker Compose with Blue/Green deployment capabilities and automated backups.

## Prerequisites

- **Docker Engine** (24.0+) & **Docker Compose Plugin** (2.20+)
- **Git**
- A Linux server (Ubuntu/Debian recommended)
- A domain name pointing to the server IP (for Caddy)

## 1. Initial Setup

1.  **Clone the Repository**:

    ```bash
    git clone <your-repo-url> /opt/subro_web
    cd /opt/subro_web
    ```

2.  **Configure Production Environment**:

    Copy the template to `.env.prod`:

    ```bash
    cp infra/prod.env.example .env.prod
    ```

    Edit `.env.prod` and set secure values:

    ```bash
    nano .env.prod
    ```

    > [!IMPORTANT]
    > Ensure `SECRET_KEY`, `POSTGRES_PASSWORD`, and `FIRST_SUPERUSER_PASSWORD` are strong and unique.

3.  **Prepare Directory Structure**:
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

This script will:

1.  Launch/Verify Gateway and Data stacks (bootstrapping `infra` project).
2.  Deploy the application stack (e.g., `blue` project).
3.  Wait for health checks.
4.  Configure Caddy to point to the new stack.

## 3. Routine Deployments (Updates)

To deploy a new version of the code:

1.  **Pull changes**:

    ```bash
    git pull origin main
    ```

2.  **Run Deployment Script**:

    ```bash
    ./infra/scripts/blue_green_deploy.sh
    ```

    The script automatically:

    - Identifies the _active_ color (e.g., Blue).
    - Builds and starts the _inactive_ color (e.g., Green).
    - Verifies health of the new stack.
    - Updates Caddy traffic.
    - Stops the old stack.

    > [!NOTE]
    > Zero downtime is achieved as Caddy waits for the new backend to be healthy before switching.

## 4. Backups

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

## 5. Troubleshooting

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
