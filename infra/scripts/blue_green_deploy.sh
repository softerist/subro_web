#!/bin/bash
set -e

# Configuration
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCK_DIR="$INFRA_DIR/docker"
CADDYFILE_PROD="$DOCK_DIR/Caddyfile.prod"
COMPOSE_APP="$DOCK_DIR/compose.prod.yml"
COMPOSE_DATA="$DOCK_DIR/compose.data.yml"
COMPOSE_GATEWAY="$DOCK_DIR/compose.gateway.yml"
ENV_FILE="$INFRA_DIR/.env.prod"

# Ensure .env.prod exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found. Please create it from $INFRA_DIR/prod.env.example"
    exit 1
fi

# Ensure Redis and QUIC sysctls are set on host (persistent)
SYSCTL_REDIS_CONF="/etc/sysctl.d/99-redis.conf"
SYSCTL_CADDY_CONF="/etc/sysctl.d/99-caddy.conf"
if [ -w "/etc" ]; then
    if [ ! -f "$SYSCTL_REDIS_CONF" ] || ! grep -q "^vm.overcommit_memory=1$" "$SYSCTL_REDIS_CONF"; then
        echo "Applying vm.overcommit_memory=1 to $SYSCTL_REDIS_CONF"
        echo "vm.overcommit_memory=1" > "$SYSCTL_REDIS_CONF"
    fi
    if [ ! -f "$SYSCTL_CADDY_CONF" ] \
        || ! grep -q "^net.core.rmem_max=7500000$" "$SYSCTL_CADDY_CONF" \
        || ! grep -q "^net.core.wmem_max=7500000$" "$SYSCTL_CADDY_CONF"; then
        echo "Applying QUIC UDP buffer sysctls to $SYSCTL_CADDY_CONF"
        printf "%s\n" "net.core.rmem_max=7500000" "net.core.wmem_max=7500000" > "$SYSCTL_CADDY_CONF"
    fi
    sysctl --system >/dev/null 2>&1 || true
else
    echo "Warning: Cannot write to /etc/sysctl.d (insufficient permissions)."
    echo "Please set vm.overcommit_memory=1, net.core.rmem_max=7500000, net.core.wmem_max=7500000 on the host."
fi

# 0. Clean up potential conflicting manual networks (optional, for safety)
# docker network rm infra_internal_net infra_caddy_net 2>/dev/null || true
# We rely on compose to create them correctly.

# 0.5 Stop Development Stack (if running)
echo "--- Stopping Development Stack (if running) ---"
docker compose -p subapp_dev -f "$DOCK_DIR/docker-compose.yml" -f "$DOCK_DIR/docker-compose.override.yml" down 2>/dev/null || true

# 1. Ensure Infrastructure (Gateway + Data) is running
echo "--- Ensuring Infrastucture is Up ---"
docker compose --env-file "$ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" -f "$COMPOSE_DATA" up -d --build

# 1. Determine Active Color
# We check if 'blue-api-1' is running. If so, next is green.
if docker ps --format '{{.Names}}' | grep -q "blue-api-1"; then
    CURRENT_COLOR="blue"
    NEW_COLOR="green"
else
    CURRENT_COLOR="green"
    NEW_COLOR="blue"
fi

echo "--- Deployment Started ---"
echo "Current Color: $CURRENT_COLOR"
echo "Deploying New Color: $NEW_COLOR"

# 2. Deploy New Color
echo "--- Starting $NEW_COLOR Stack ---"
# We define project name as the color
docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" up --build -d

# 3. Wait for Health
echo "--- Waiting for Health Checks ($NEW_COLOR) ---"
# Loop to check health of api container
API_CONTAINER="$NEW_COLOR-api-1"
MAX_RETRIES=30
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
    echo "Error: New deployment ($NEW_COLOR) failed health check. Aborting."
    echo "Logs:"
    docker logs --tail 50 "$API_CONTAINER"
    # Cleanup new deployment
    docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" down
    exit 1
fi

echo "--- New Color ($NEW_COLOR) is Healthy ---"

# 3.5 Run Database Migrations
echo "--- Running Database Migrations ---"
# We run migration using the new API container
if ! docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" exec -T api poetry run alembic upgrade head; then
    echo "Error: Database migration failed. Aborting."
    docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" down
    exit 1
fi
echo "--- Migrations Completed ---"

# 3.6 Re-encrypt Encrypted Fields (key rotation)
if [ "${REENCRYPT_ON_DEPLOY:-1}" != "0" ]; then
    echo "--- Re-encrypting Encrypted Fields (if rotation active) ---"
    REENCRYPT_ARGS=()
    if [ "${REENCRYPT_FORCE:-0}" = "1" ]; then
        REENCRYPT_ARGS+=("--force")
    fi
    if ! docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" exec -T api python /app/scripts/reencrypt_encrypted_fields.py "${REENCRYPT_ARGS[@]}"; then
        echo "Error: Re-encryption failed. Aborting."
        docker compose --env-file "$ENV_FILE" -p "$NEW_COLOR" -f "$COMPOSE_APP" down
        exit 1
    fi
    echo "--- Re-encryption Step Completed ---"
else
    echo "--- Re-encryption Skipped (REENCRYPT_ON_DEPLOY=0) ---"
fi

# 4. Switch Traffic (Update Caddy)
echo "--- Switching Traffic to $NEW_COLOR ---"

# We use sed to replace the upstream in Caddyfile.prod
# Template: reverse_proxy api:8000 -> reverse_proxy <color>-api-1:8000
# And frontend:8080 -> <color>-frontend-1:8080
# BUT, since we overwrite the file, we should maintain a template.
# Let's assume Caddyfile.prod IS the template but we need to inject the color.
# Actually, it's safer to have Caddyfile.template.
# For this iteration, I will create a template on the fly or sed the live file carefully.

# Create a temporary Caddyfile from a fixed template or backup?
# I'll rely on a Caddyfile.template file. If it doesn't exist, I'll create it from Caddyfile.prod first time.
TEMPLATE="$DOCK_DIR/Caddyfile.template"
if [ ! -f "$TEMPLATE" ]; then
    echo "Creating Caddyfile.template from Caddyfile.prod..."
    cp "$CADDYFILE_PROD" "$TEMPLATE"
fi

# Prepare new Caddyfile content
# We replace placeholders with actual container names
sed "s/{{UPSTREAM_API}}/$NEW_COLOR-api-1/g; s/{{UPSTREAM_FRONTEND}}/$NEW_COLOR-frontend-1/g" "$TEMPLATE" > "$CADDYFILE_PROD"

# Reload Caddy (in infra project)
docker compose --env-file "$ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" exec caddy caddy reload --config /etc/caddy/Caddyfile.prod

echo "--- Traffic Switched ---"

# 5. Cleanup Old Color
if [ -n "$CURRENT_COLOR" ]; then
    # Double check we are not killing the new color
    if [ "$CURRENT_COLOR" != "$NEW_COLOR" ]; then
        echo "--- Stopping Old Color ($CURRENT_COLOR) ---"
        docker compose --env-file "$ENV_FILE" -p "$CURRENT_COLOR" -f "$COMPOSE_APP" down
    fi
fi

echo "--- Deployment Complete ($NEW_COLOR Active) ---"
