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


# ------------------------------------------------------------------------------
# Logging Helpers
# ------------------------------------------------------------------------------

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%dT%H:%M:%S%z')]${NC} $*"
}

success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%dT%H:%M:%S%z')] ✓ $*${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%dT%H:%M:%S%z')] ⚠️  $*${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%dT%H:%M:%S%z')] ❌ $*${NC}"
}

section_start() {
    local section_id=$1
    local section_title=$2
    local collapsed=${3:-true}
    local collapsed_str=""
    if [ "$collapsed" = "true" ]; then
        collapsed_str="[collapsed=true]"
    fi
    echo -e "\e[0Ksection_start:$(date +%s):${section_id}${collapsed_str}\r\e[0K${BLUE}>>> ${section_title}${NC}"
    log "Starting: $section_title"
}

section_end() {
    local section_id=$1
    echo -e "\e[0Ksection_end:$(date +%s):${section_id}\r\e[0K"
}

# Retry helper for docker compose pull (handles registry timeouts)
docker_compose_pull_with_retry() {
    local max_attempts=3
    local attempt=1
    local wait_time=5

    log "Pulling Docker images with retry (max $max_attempts attempts)..."
    while [ $attempt -le $max_attempts ]; do
        # Parallel is now default in modern docker compose
        if docker compose --progress=plain "$@" pull; then
            success "Docker pull successful!"
            return 0
        fi
        if [ $attempt -eq $max_attempts ]; then
            error "Docker pull failed after $max_attempts attempts."
            return 1
        fi
        warn "Docker pull failed (attempt $attempt/$max_attempts). Retrying in ${wait_time}s..."
        sleep $wait_time
        wait_time=$((wait_time * 2))
        attempt=$((attempt + 1))
    done
}

log "--- Staging Deployment Started ---"

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

section_start "stage_pull" "Pulling and Starting Staging App Stack"
# We manage the app + data stack here for staging isolation.
log "Verifying Images Exist..."
for img in "$DOCKER_IMAGE_API" "$DOCKER_IMAGE_WORKER" "$DOCKER_IMAGE_FRONTEND" "$DOCKER_IMAGE_BACKUP"; do
    log "Checking for $img..."
    # Add timeout to prevent hanging on slow registry responses
    if ! timeout 30s docker manifest inspect "$img" > /dev/null 2>&1; then
        warn "Image $img not found or registry timeout."
    else
        success "Image $img found"
    fi
done

docker_compose_pull_with_retry --env-file "$ENV_FILE" -p subro_staging \
    -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" -f "$COMPOSE_DATA"

# We don't use blue-green for staging to save resources
log "Starting containers..."
docker compose --progress=plain --env-file "$ENV_FILE" -p subro_staging \
    -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" -f "$COMPOSE_DATA" up -d --scale scheduler=0
section_end "stage_pull"

# Wait for Health
section_start "stage_health" "Waiting for Health Checks (staging)"
API_CONTAINER="subro_staging-api-1"
MAX_RETRIES=40  # 40 * 5s = ~3.5 min max
COUNT=0
HEALTHY=false

wait_with_keepalive() {
    local seconds=$1
    local i=0
    while [ $i -lt $seconds ]; do
        sleep 1
        echo "."  # Newline ensures flush
        i=$((i+1))
    done
}

# Give containers time to initialize before first health check
# Give containers time to initialize before first health check
log "Waiting 10s for containers to initialize..."
wait_with_keepalive 10

while [ $COUNT -lt $MAX_RETRIES ]; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$API_CONTAINER" 2>/dev/null || echo "starting")
    if [ "$STATUS" == "healthy" ]; then
        HEALTHY=true
        success "Container $API_CONTAINER is healthy!"
        break
    fi
    # Print every 2nd iteration to keep SSH output flowing
    if [ $((COUNT % 2)) -eq 0 ]; then
        log "Container $API_CONTAINER status: $STATUS ($COUNT/$MAX_RETRIES)"
    fi
    wait_with_keepalive 5
    COUNT=$((COUNT+1))
done

if [ "$HEALTHY" = false ]; then
    error "Staging deployment failed health check."
    docker logs --tail 20 "$API_CONTAINER"

    log "Cleaning up failed deployment..."
    docker compose --progress=plain --env-file "$ENV_FILE" -p subro_staging \
        -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" -f "$COMPOSE_DATA" down

    exit 1
fi
section_end "stage_health"

success "Staging is Healthy"

# Run Migrations
section_start "stage_migrate" "Running Database Migrations (staging)"
docker compose --env-file "$ENV_FILE" -p subro_staging -f "$COMPOSE_APP" exec -T api poetry run alembic upgrade head
section_end "stage_migrate"

# 5. Reload Caddy (safely sync with latest staging routes)
section_start "stage_caddy" "Updating Shared Caddy Configuration"
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
    log "Shared Caddy configuration updated (Prod Color: $PROD_COLOR)"
fi

log "Recreating Caddy (picks up env changes)..."
PROJECT_ENV_FILE="$PROD_ENV_FILE" docker compose --progress=plain --env-file "$PROD_ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" -f "$COMPOSE_DATA" up -d --force-recreate caddy
section_end "stage_caddy"

# Cleanup old images to prevent disk buildup (runs in background)
section_start "stage_cleanup" "Pruning old Docker images (background)"
(docker image prune -af --filter "until=168h" >/dev/null 2>&1 &)
section_end "stage_cleanup"

success "Staging Deployment Complete"
