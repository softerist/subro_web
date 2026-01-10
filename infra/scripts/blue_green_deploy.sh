#!/bin/bash
set -e

# Configuration
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCK_DIR="$INFRA_DIR/docker"
CADDYFILE_PROD="$DOCK_DIR/Caddyfile.prod"
COMPOSE_APP="$DOCK_DIR/compose.prod.yml"
COMPOSE_DATA="$DOCK_DIR/compose.data.yml"
COMPOSE_GATEWAY="$DOCK_DIR/compose.gateway.yml"
COMPOSE_IMAGES="$DOCK_DIR/compose.prod.images.yml"
ENV_FILE="$INFRA_DIR/.env.prod"

# Export variables for compose file expansion
export PROJECT_ENV_FILE="$ENV_FILE"
export NETWORK_NAME="infra_internal_net"
export NETWORK_EXTERNAL="true"

# Ensure .env.prod exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found. Please create it from $INFRA_DIR/.env.prod.example"
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
        if docker compose "$@" pull; then
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

# Ensure Redis and QUIC sysctls are set on host (persistent)
section_start "prod_sysctl" "Applying Sysctl Tweaks"
SYSCTL_REDIS_CONF="/etc/sysctl.d/99-redis.conf"
SYSCTL_CADDY_CONF="/etc/sysctl.d/99-caddy.conf"
if [ -w "/etc" ]; then
    if [ ! -f "$SYSCTL_REDIS_CONF" ] || ! grep -q "^vm.overcommit_memory=1$" "$SYSCTL_REDIS_CONF"; then
        log "Applying vm.overcommit_memory=1 to $SYSCTL_REDIS_CONF"
        echo "vm.overcommit_memory=1" > "$SYSCTL_REDIS_CONF"
    fi
    if [ ! -f "$SYSCTL_CADDY_CONF" ] \
        || ! grep -q "^net.core.rmem_max=7500000$" "$SYSCTL_CADDY_CONF" \
        || ! grep -q "^net.core.wmem_max=7500000$" "$SYSCTL_CADDY_CONF"; then
        log "Applying QUIC UDP buffer sysctls to $SYSCTL_CADDY_CONF"
        printf "%s\n" "net.core.rmem_max=7500000" "net.core.wmem_max=7500000" > "$SYSCTL_CADDY_CONF"
    fi
    sysctl --system >/dev/null 2>&1 || true
else
    warn "Cannot write to /etc/sysctl.d (insufficient permissions)."
    warn "Please set vm.overcommit_memory=1, net.core.rmem_max=7500000, net.core.wmem_max=7500000 on the host."
fi
section_end "prod_sysctl"

# 0. Clean up potential conflicting manual networks (optional, for safety)
# 0.5 Stop Development Stack (if running)
log "Stopping Development Stack (if running)..."
docker compose -p subapp_dev -f "$DOCK_DIR/docker-compose.yml" -f "$DOCK_DIR/docker-compose.override.yml" down 2>/dev/null || true

# 0.9 Ensure Caddyfile.prod exists BEFORE starting infrastructure
# This prevents Caddy from using dev config on first boot
section_start "prod_caddyfile_init" "Initializing Caddyfile.prod"
TEMPLATE="$DOCK_DIR/Caddyfile.template"
TMP_CADDYFILE="$CADDYFILE_PROD.tmp"

if [ ! -f "$TEMPLATE" ]; then
    error "Caddyfile.template not found at $TEMPLATE"
    exit 1
fi

# Determine which color to route to (prefer existing active, fallback to blue)
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "green-api-1"; then
    INIT_COLOR="green"
elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q "blue-api-1"; then
    INIT_COLOR="blue"
else
    INIT_COLOR="blue"  # Default to blue for fresh deployments
fi

DOMAIN_NAME=$(grep -E "^DOMAIN_NAME=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
if [ -z "$DOMAIN_NAME" ]; then
    error "DOMAIN_NAME not found in $ENV_FILE"
    exit 1
fi

# Only regenerate if empty or missing (preserve existing config if valid)
if [ ! -s "$CADDYFILE_PROD" ]; then
    log "Generating initial Caddyfile.prod (routing to $INIT_COLOR)..."
    sed "s/{{UPSTREAM_API}}/$INIT_COLOR-api-1/g; s/{{UPSTREAM_FRONTEND}}/$INIT_COLOR-frontend-1/g; s/{\\\$DOMAIN_NAME}/$DOMAIN_NAME/g" "$TEMPLATE" > "$TMP_CADDYFILE"

    if [ -s "$TMP_CADDYFILE" ]; then
        mv "$TMP_CADDYFILE" "$CADDYFILE_PROD"
        success "Caddyfile.prod initialized"
    else
        error "Failed to generate Caddyfile.prod: Output is empty"
        rm -f "$TMP_CADDYFILE"
        exit 1
    fi
else
    log "Caddyfile.prod already exists, skipping initialization"
fi
section_end "prod_caddyfile_init"

# 1. Ensure Infrastructure (Gateway + Data) is running
section_start "prod_infra" "Ensuring Infrastucture is Up"
if [ "${USE_PREBUILT_IMAGES:-0}" = "1" ]; then
    docker_compose_pull_with_retry --env-file "$ENV_FILE" -p infra \
        -f "$COMPOSE_GATEWAY" -f "$COMPOSE_DATA" -f "$COMPOSE_IMAGES"
    docker compose --env-file "$ENV_FILE" -p infra \
        -f "$COMPOSE_GATEWAY" -f "$COMPOSE_DATA" -f "$COMPOSE_IMAGES" up -d
else
    # Build locally if no prebuilt images
    docker compose --env-file "$ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" -f "$COMPOSE_DATA" up -d --build
fi
section_end "prod_infra"

if docker ps --format '{{.Names}}' | grep -q "blue-api-1"; then
    CURRENT_COLOR="blue"
    NEW_COLOR="green"
else
    CURRENT_COLOR="green"
    NEW_COLOR="blue"
fi

log "--- Deployment Started ---"
log "Current Color: $CURRENT_COLOR"
log "Deploying New Color: $NEW_COLOR"

# 2. Deploy New Color
section_start "prod_deploy" "Starting $NEW_COLOR Stack"
if [ "${USE_PREBUILT_IMAGES:-0}" = "1" ]; then
    log "Using pre-built images from registry..."
    # Pull images explicitly with retry (using overlay)
    docker_compose_pull_with_retry --env-file "$ENV_FILE" -p "$NEW_COLOR" \
        -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES"

    # Start WITHOUT --build (using overlay)
    docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" \
        -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" up -d
else
    # Build locally
    docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" up --build -d
fi
section_end "prod_deploy"

# 3. Wait for Health
section_start "prod_health" "Waiting for Health Checks ($NEW_COLOR)"
# Loop to check health of api container (faster polling)
API_CONTAINER="$NEW_COLOR-api-1"
MAX_RETRIES=40  # 40 * 3s = 2 min max
COUNT=0
HEALTHY=false

while [ $COUNT -lt $MAX_RETRIES ]; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$API_CONTAINER" 2>/dev/null || echo "starting")
    if [ "$STATUS" == "healthy" ]; then
        HEALTHY=true
        success "Container $API_CONTAINER is healthy!"
        break
    fi
    # Only print every 5th check to reduce noise
    if [ $((COUNT % 5)) -eq 0 ]; then
        log "Container $API_CONTAINER status: $STATUS ($COUNT/$MAX_RETRIES)"
    fi
    sleep 3  # Faster polling (was 5s)
    COUNT=$((COUNT+1))
done

if [ "$HEALTHY" = false ]; then
    error "New deployment ($NEW_COLOR) failed health check. Aborting."
    echo "Logs:"
    docker logs --tail 50 "$API_CONTAINER"
    # Cleanup new deployment
    if [ "${USE_PREBUILT_IMAGES:-0}" = "1" ]; then
        docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" down
    else
        docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" down
    fi
    exit 1
fi
section_end "prod_health"

success "New Color ($NEW_COLOR) is Healthy"

# 3.4 Stop OLD worker BEFORE traffic switch (prevent job duplication)
# We do this logic in the open, small enough not to need a section usually, but let's be cleaner
if [ -n "$CURRENT_COLOR" ] && [ "$CURRENT_COLOR" != "$NEW_COLOR" ]; then
    log "Stopping old worker to prevent job duplication..."
    docker compose --env-file "$ENV_FILE" -p "$CURRENT_COLOR" -f "$COMPOSE_APP" stop worker || true
fi

# 3.5 Run Database Migrations
section_start "prod_migrate" "Running Database Maintenance"
log "Running Database Migrations..."
# We run migration using the new API container
if ! docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" exec -T api poetry run alembic upgrade head; then
    error "Database migration failed. Aborting."
    if [ "${USE_PREBUILT_IMAGES:-0}" = "1" ]; then
        docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" down
    else
        docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" down
    fi
    exit 1
fi
success "Migrations Completed"

# 3.6 Re-encrypt Encrypted Fields (key rotation)
if [ "${REENCRYPT_ON_DEPLOY:-1}" != "0" ]; then
    log "Re-encrypting Encrypted Fields (if rotation active)..."
    REENCRYPT_ARGS=()
    if [ "${REENCRYPT_FORCE:-0}" = "1" ]; then
        REENCRYPT_ARGS+=("--force")
    fi
    if ! docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" exec -T api python /app/scripts/reencrypt_encrypted_fields.py "${REENCRYPT_ARGS[@]}"; then
        error "Re-encryption failed. Aborting."
        if [ "${USE_PREBUILT_IMAGES:-0}" = "1" ]; then
            docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" -f "$COMPOSE_IMAGES" down
        else
            docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" down
        fi
        exit 1
    fi
    success "Re-encryption Step Completed"
else
    log "Re-encryption Skipped (REENCRYPT_ON_DEPLOY=0)"
fi

# 3.7 Sync Database Version
log "Syncing Database Version..."
if ! docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" exec -T api python /app/scripts/sync_db_version.py; then
    warn "Database version sync failed. Continuing deployment..."
fi
success "Database Version Sync Completed"
section_end "prod_migrate"

# 4. Switch Traffic (Update Caddy)
section_start "prod_switch" "Switching Traffic to $NEW_COLOR"

TEMPLATE="$DOCK_DIR/Caddyfile.template"
if [ ! -f "$TEMPLATE" ]; then
    log "Creating Caddyfile.template from Caddyfile.prod..."
    cp "$CADDYFILE_PROD" "$TEMPLATE"
fi

# Prepare new Caddyfile content
# Read DOMAIN_NAME from env file for expansion
DOMAIN_NAME=$(grep -E "^DOMAIN_NAME=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
if [ -z "$DOMAIN_NAME" ]; then
    error "DOMAIN_NAME not found in $ENV_FILE"; exit 1
fi
sed "s/{{UPSTREAM_API}}/$NEW_COLOR-api-1/g; s/{{UPSTREAM_FRONTEND}}/$NEW_COLOR-frontend-1/g; s/{\\\$DOMAIN_NAME}/$DOMAIN_NAME/g" "$TEMPLATE" > "$TMP_CADDYFILE"

if [ ! -s "$TMP_CADDYFILE" ]; then
    error "Failed to generate Caddyfile.prod (switch phase): Output is empty"
    rm -f "$TMP_CADDYFILE"
    exit 1
fi
mv "$TMP_CADDYFILE" "$CADDYFILE_PROD"

# Reload Caddy by restarting the container (exec reload doesn't always pick up bind-mount changes)
log "Restarting Caddy to apply new configuration..."
docker compose --env-file "$ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" restart caddy

# Verify Caddy is routing to the new color
sleep 3
CADDY_UPSTREAM=$(docker compose --env-file "$ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" exec -T caddy grep -m1 "reverse_proxy" /etc/caddy/Caddyfile.prod 2>/dev/null || echo "")
if echo "$CADDY_UPSTREAM" | grep -q "$NEW_COLOR"; then
    success "Caddy now routing to $NEW_COLOR"
else
    warn "Caddy config verification failed - check /etc/caddy/Caddyfile.prod inside container"
fi

success "Traffic Switched"

# Verify API responds correctly via the new routing
log "Verifying API health via Caddy..."
API_RESPONSE=$(docker compose --env-file "$ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" exec -T caddy \
    wget -q -O - --timeout=10 "http://$NEW_COLOR-api-1:8000/api/v1/" 2>/dev/null || echo "")
if echo "$API_RESPONSE" | grep -q '"version"'; then
    API_VERSION=$(echo "$API_RESPONSE" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p')
    success "API responding correctly (version: $API_VERSION)"
else
    warn "API health check failed - response: $API_RESPONSE"
fi

section_end "prod_switch"

# 5. Cleanup Inactive Color (and any orphaned containers)
section_start "prod_cleanup" "Cleanup Inactive Color"
for color in blue green; do
    if [ "$color" != "$NEW_COLOR" ]; then
        if docker ps -a --format '{{.Names}}' | grep -q "^$color-"; then
            log "Cleaning up old/orphaned $color containers..."
            docker compose --env-file "$ENV_FILE" -p "$color" -f "$COMPOSE_APP" down || true
        fi
    fi
done

log "Pruning old images in background..."
# Remove dangling images only, preserve tagged images for rollback (older than 1 week)
(docker image prune -f --filter "until=168h" >/dev/null 2>&1 &)
section_end "prod_cleanup"

# 7. Post-Deployment Hooks
section_start "prod_hooks" "Running Post-Deployment Hooks"

# Create directories on host for qBittorrent integration
log "Creating /opt/subro_web directories..."
mkdir -p /opt/subro_web/scripts /opt/subro_web/secrets /opt/subro_web/logs

# Copy webhook script from Docker container to host
# (The script runs on the HOST where qBittorrent is, not inside Docker)
log "Copying webhook script from container to host..."
if docker cp "$NEW_COLOR-api-1:/app/scripts/qbittorrent-nox-webhook.sh" /opt/subro_web/scripts/; then
    chmod +x /opt/subro_web/scripts/qbittorrent-nox-webhook.sh
    success "Webhook script copied to /opt/subro_web/scripts/"
else
    warn "Failed to copy webhook script (container may not have it)"
fi

# Set ownership for qbittorrent-nox user
log "Setting permissions for qbittorrent-nox..."
chown -R qbittorrent-nox:qbittorrent-nox /opt/subro_web/scripts /opt/subro_web/logs 2>/dev/null || true
chmod -R 775 /opt/subro_web/logs

section_end "prod_hooks"

success "Deployment Complete ($NEW_COLOR Active)"
