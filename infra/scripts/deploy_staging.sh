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

# Ensure .env.staging exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found."
    exit 1
fi

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
docker compose --env-file "$ENV_FILE" -p subro_staging \
    -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" -f "$COMPOSE_DATA" pull

# We don't use blue-green for staging to save resources
docker compose --env-file "$ENV_FILE" -p subro_staging \
    -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" -f "$COMPOSE_DATA" up -d --scale scheduler=0

# Wait for Health
echo "--- Waiting for Health Checks (staging) ---"
API_CONTAINER="subro_staging-api-1"
MAX_RETRIES=20
COUNT=0
HEALTHY=false

while [ $COUNT -lt $MAX_RETRIES ]; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$API_CONTAINER" 2>/dev/null || echo "starting")
    echo "Container $API_CONTAINER status: $STATUS"

    if [ "$STATUS" == "healthy" ]; then
        HEALTHY=true
        break
    fi
    sleep 5
    COUNT=$((COUNT+1))
done

if [ "$HEALTHY" = false ]; then
    echo "Error: Staging deployment failed health check."
    docker logs --tail 20 "$API_CONTAINER"
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
# Note: This assumes production is in /opt/subro_web
PROD_CADDYFILE="/opt/subro_web/infra/docker/Caddyfile.prod"
if [ -d "/opt/subro_web/infra/docker" ]; then
    sed "s/{{UPSTREAM_API}}/$PROD_COLOR-api-1/g; s/{{UPSTREAM_FRONTEND}}/$PROD_COLOR-frontend-1/g" "$DOCK_DIR/Caddyfile.template" > "$PROD_CADDYFILE"
    echo "Shared Caddy configuration updated (Prod Color: $PROD_COLOR)"
fi

echo "--- Recreating Caddy (picks up env changes) ---"
docker compose --env-file /opt/subro_web/infra/.env.prod -p infra -f "$COMPOSE_GATEWAY" -f "$COMPOSE_DATA" up -d --force-recreate caddy

echo "--- Staging Deployment Complete ---"
