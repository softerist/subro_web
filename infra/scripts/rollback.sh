#!/bin/bash
set -e

# Configuration
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCK_DIR="$INFRA_DIR/docker"
CADDYFILE_PROD="$DOCK_DIR/Caddyfile.prod"
COMPOSE_APP="$DOCK_DIR/compose.prod.yml"
ENV_FILE="$INFRA_DIR/.env.prod"

# Export variables for compose file expansion
export PROJECT_ENV_FILE="$ENV_FILE"
export NETWORK_NAME="infra_internal_net"
export NETWORK_EXTERNAL="true"

echo "--- Rollback Initiated ---"

# 1. Determine Current Active Color (Bad)
if docker ps --format '{{.Names}}' | grep -q "blue-api-1"; then
    CURRENT_MALFUNCTIONING_COLOR="blue"
    OLD_WORKING_COLOR="green"
elif docker ps --format '{{.Names}}' | grep -q "green-api-1"; then
    CURRENT_MALFUNCTIONING_COLOR="green"
    OLD_WORKING_COLOR="blue"
else
    echo "Error: Could not determine active color. Manual intervention required."
    exit 1
fi

echo "Current Bad Color: $CURRENT_MALFUNCTIONING_COLOR"
echo "Attempting to rollback to: $OLD_WORKING_COLOR"

# 2. Check if Old Color exists
if ! docker ps -a --format '{{.Names}}' | grep -q "${OLD_WORKING_COLOR}-api-1"; then
    echo "Error: Old color ($OLD_WORKING_COLOR) containers not found. Cannot rollback automatically."
    exit 1
fi

# 3. Start Old Color
echo "--- Starting Old Color ($OLD_WORKING_COLOR) ---"
# We use 'docker start' to resume the existing containers with their old configuration/images
docker start "${OLD_WORKING_COLOR}-api-1" "${OLD_WORKING_COLOR}-worker-1" "${OLD_WORKING_COLOR}-frontend-1"

# 4. Wait for Health of Old Color
echo "--- Waiting for Health ($OLD_WORKING_COLOR) ---"
API_CONTAINER="${OLD_WORKING_COLOR}-api-1"
MAX_RETRIES=30
COUNT=0
HEALTHY=false

while [ $COUNT -lt $MAX_RETRIES ]; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$API_CONTAINER" 2>/dev/null || echo "starting")
    if [ "$STATUS" == "healthy" ]; then
        HEALTHY=true
        break
    fi
    sleep 2
    COUNT=$((COUNT+1))
done

if [ "$HEALTHY" = false ]; then
    echo "Error: Old color ($OLD_WORKING_COLOR) failed to recover. Aborting rollback."
    exit 1
fi

# 5. Switch Traffic to Old Color
echo "--- Switching Traffic to $OLD_WORKING_COLOR ---"
TEMPLATE="$DOCK_DIR/Caddyfile.template"
# Update Caddyfile
# Read DOMAIN_NAME from env file for expansion
DOMAIN_NAME=$(grep -E "^DOMAIN_NAME=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
if [ -z "$DOMAIN_NAME" ]; then
    echo "Error: DOMAIN_NAME not found in $ENV_FILE"
    # Don't exit here to allow manual intervention, but warn loudly
fi
# Update Caddyfile
sed "s/{{UPSTREAM_API}}/$OLD_WORKING_COLOR-api-1/g; s/{{UPSTREAM_FRONTEND}}/$OLD_WORKING_COLOR-frontend-1/g; s/{\\\$DOMAIN_NAME}/$DOMAIN_NAME/g" "$TEMPLATE" > "$CADDYFILE_PROD"

# Reload Caddy
COMPOSE_GATEWAY="$DOCK_DIR/compose.gateway.yml"
docker compose --env-file "$ENV_FILE" -p infra -f "$COMPOSE_GATEWAY" exec -T caddy caddy reload --config /etc/caddy/Caddyfile.prod

# 6. Stop Bad Color
echo "--- Stopping Bad Color ($CURRENT_MALFUNCTIONING_COLOR) ---"
docker compose --env-file "$ENV_FILE" -p "$CURRENT_MALFUNCTIONING_COLOR" -f "$COMPOSE_APP" stop

echo "--- Rollback Complete ($OLD_WORKING_COLOR Active) ---"
