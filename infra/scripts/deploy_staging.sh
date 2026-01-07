#!/bin/bash
set -e

# Configuration
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCK_DIR="$INFRA_DIR/docker"
COMPOSE_APP="$DOCK_DIR/compose.prod.yml"
COMPOSE_IMAGES="$DOCK_DIR/compose.prod.images.yml"
COMPOSE_DATA="$DOCK_DIR/compose.data.yml"
COMPOSE_GATEWAY="$DOCK_DIR/compose.gateway.yml"
ENV_FILE="$INFRA_DIR/.env.staging"
# Production infra directory (where Caddy config and .env.prod live on the server)
PROD_INFRA_DIR="${PROD_INFRA_DIR:-/opt/subro_web/infra}"

# Ensure .env.staging exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found."
    exit 1
fi

# Retry helper for docker compose pull (handles registry timeouts)
docker_compose_pull_with_retry() {
    local max_attempts=3
    local attempt=1
    local wait_time=5

    echo "Pulling Docker images with retry (max $max_attempts attempts)..."
    while [ $attempt -le $max_attempts ]; do
        # Parallel is now default in modern docker compose
        if docker compose "$@" pull; then
            echo "Docker pull successful!"
            return 0
        fi
        if [ $attempt -eq $max_attempts ]; then
            echo "ERROR: Docker pull failed after $max_attempts attempts."
            return 1
        fi
        echo "Docker pull failed (attempt $attempt/$max_attempts). Retrying in ${wait_time}s..."
        sleep $wait_time
        wait_time=$((wait_time * 2))
        attempt=$((attempt + 1))
    done
}

echo "--- Staging Deployment Started ---"

# Export variables for compose file expansion
export PROJECT_ENV_FILE="$ENV_FILE"
export NETWORK_NAME="infra_internal_net"
export NETWORK_EXTERNAL="true"

# Deploy Staging using a different project name
export DOCKER_IMAGE_API=${DOCKER_IMAGE_API:-"subro-api:latest"}
export DOCKER_IMAGE_WORKER=${DOCKER_IMAGE_WORKER:-"subro-worker:latest"}
export DOCKER_IMAGE_FRONTEND=${DOCKER_IMAGE_FRONTEND:-"subro-frontend:latest"}
export DOCKER_IMAGE_BACKUP=${DOCKER_IMAGE_BACKUP:-"subro-backup:latest"}
export BACKUP_PREFIX="staging_"

echo "--- Pulling/Starting Staging App Stack (with isolated Data) ---"
# We manage the app + data stack here for staging isolation.
echo "--- Verifying Images Exist ---"
for img in "$DOCKER_IMAGE_API" "$DOCKER_IMAGE_WORKER" "$DOCKER_IMAGE_FRONTEND" "$DOCKER_IMAGE_BACKUP"; do
    echo "Checking for $img..."
    if ! docker manifest inspect "$img" > /dev/null 2>&1; then
        echo "⚠️  WARNING: Image $img not found in registry (manifest check failed)."
        echo "    Trying to pull it directly to confirm..."
    fi
done

docker_compose_pull_with_retry --env-file "$ENV_FILE" -p subro_staging \
    -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" -f "$COMPOSE_DATA"

# We don't use blue-green for staging to save resources
docker compose --env-file "$ENV_FILE" -p subro_staging \
    -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" -f "$COMPOSE_DATA" up -d --scale scheduler=0

# Wait for Health (faster polling)
echo "--- Waiting for Health Checks (staging) ---"
API_CONTAINER="subro_staging-api-1"
MAX_RETRIES=30  # 30 * 3s = 1.5 min max
COUNT=0
HEALTHY=false

while [ $COUNT -lt $MAX_RETRIES ]; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$API_CONTAINER" 2>/dev/null || echo "starting")
    if [ "$STATUS" == "healthy" ]; then
        HEALTHY=true
        echo "Container $API_CONTAINER is healthy!"
        break
    fi
    # Only print every 5th check
    if [ $((COUNT % 5)) -eq 0 ]; then
        echo "Container $API_CONTAINER status: $STATUS ($COUNT/$MAX_RETRIES)"
    fi
    sleep 3  # Faster polling
    COUNT=$((COUNT+1))
done

if [ "$HEALTHY" = false ]; then
    echo "Error: Staging deployment failed health check."
    docker logs --tail 20 "$API_CONTAINER"

    echo "--- Cleaning up failed deployment ---"
    docker compose --env-file "$ENV_FILE" -p subro_staging \
        -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" -f "$COMPOSE_DATA" down

    exit 1
fi

echo "--- Staging is Healthy ---"

# Run Migrations
echo "--- Running Database Migrations (staging) ---"
docker compose --env-file "$ENV_FILE" -p subro_staging -f "$COMPOSE_APP" exec -T api poetry run alembic upgrade head

# 5. Reload Caddy (safely sync with latest staging routes)
echo "--- Updating Shared Caddy Configuration ---"
# Detect current production color to avoid breaking it
if docker ps --format '{{.Names}}' | grep -q "blue-api-1"; then
    PROD_COLOR="blue"
elif docker ps --format '{{.Names}}' | grep -q "green-api-1"; then
    PROD_COLOR="green"
else
    # Fallback to blue if production is not found (might be first deploy)
    PROD_COLOR="blue"
fi

# Update the shared Caddyfile using the latest template from this deployment
PROD_CADDYFILE="$PROD_INFRA_DIR/docker/Caddyfile.prod"
PROD_ENV_FILE="$PROD_INFRA_DIR/.env.prod"
if [ -d "$PROD_INFRA_DIR/docker" ]; then
    sed "s/{{UPSTREAM_API}}/$PROD_COLOR-api-1/g; s/{{UPSTREAM_FRONTEND}}/$PROD_COLOR-frontend-1/g" "$DOCK_DIR/Caddyfile.template" > "$PROD_CADDYFILE"
    echo "Shared Caddy configuration updated (Prod Color: $PROD_COLOR)"
fi

echo "--- Recreating Caddy (picks up env changes) ---"
PROJECT_ENV_FILE="$PROD_ENV_FILE" docker compose --env-file "$PROD_ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" -f "$COMPOSE_DATA" up -d --force-recreate caddy

# Cleanup old images to prevent disk buildup (runs in background)
echo "--- Pruning old Docker images (background) ---"
(docker image prune -af --filter "until=168h" >/dev/null 2>&1 &)

echo "--- Staging Deployment Complete ---"
