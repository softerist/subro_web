#!/bin/bash
set -e

# Configuration
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCK_DIR="$INFRA_DIR/docker"
COMPOSE_APP="$DOCK_DIR/compose.prod.yml"
COMPOSE_IMAGES="$DOCK_DIR/compose.prod.images.yml"
ENV_FILE="$INFRA_DIR/.env.staging"

# Ensure .env.staging exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found."
    exit 1
fi

echo "--- Staging Deployment Started ---"

# Deploy Staging using a different project name
export DOCKER_IMAGE_API=${DOCKER_IMAGE_API:-"subro-api:latest"}
export DOCKER_IMAGE_WORKER=${DOCKER_IMAGE_WORKER:-"subro-worker:latest"}
export DOCKER_IMAGE_FRONTEND=${DOCKER_IMAGE_FRONTEND:-"subro-frontend:latest"}

echo "--- Ensuring Infrastucture is Up ---"
COMPOSE_GATEWAY="$DOCK_DIR/compose.gateway.yml"
COMPOSE_DATA="$DOCK_DIR/compose.data.yml"
docker compose --env-file "$ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" -f "$COMPOSE_DATA" up -d --build

echo "--- Pulling/Starting Staging Stack ---"
docker compose --env-file "$ENV_FILE" -p subro_staging \
    -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" pull

# We don't use blue-green for staging to save resources
docker compose --env-file "$ENV_FILE" -p subro_staging \
    -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" up -d

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

# Reload Caddy to recognize staging domain
echo "--- Reloading Caddy ---"
docker compose --env-file "$ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" exec -T caddy caddy reload --config /etc/caddy/Caddyfile.prod

echo "--- Staging Deployment Complete ---"
