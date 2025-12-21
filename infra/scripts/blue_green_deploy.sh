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

# 0. Create networks if they don't exist
echo "--- Ensuring Networks Exist ---"
docker network create infra_internal_net 2>/dev/null || echo "Network infra_internal_net already exists"
docker network create infra_caddy_net 2>/dev/null || echo "Network infra_caddy_net already exists"

# 1. Ensure Infrastructure (Gateway + Data) is running
echo "--- Ensuring Infrastructure is Up ---"
docker compose -p infra -f "$COMPOSE_GATEWAY" -f "$COMPOSE_DATA" up -d

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
docker compose -p "$NEW_COLOR" -f "$COMPOSE_APP" up --build -d

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
    docker compose -p "$NEW_COLOR" -f "$COMPOSE_APP" down
    exit 1
fi

echo "--- New Color ($NEW_COLOR) is Healthy ---"

# 3.5 Run Database Migrations
echo "--- Running Database Migrations ---"
# We run migration using the new API container
if ! docker compose -p "$NEW_COLOR" -f "$COMPOSE_APP" exec -T api poetry run alembic upgrade head; then
    echo "Error: Database migration failed. Aborting."
    docker compose -p "$NEW_COLOR" -f "$COMPOSE_APP" down
    exit 1
fi
echo "--- Migrations Completed ---"

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
    # Replace hardcoded 'api:8000' and 'frontend:8080' with placeholders if necessary,
    # OR just use the current Caddyfile.prod (which has api:8000) as base is risky if it was already modified?
    # Actually, Caddyfile.prod has 'api:8000'.
    # If I deploy 'blue', I want 'blue-api-1:8000'.
    # So the template should ideally have placeholders.
    # Let's assume the user will commit Caddyfile.prod as the "Source of Truth" with generic names?
    # No, generic names don't work for specific container targeting.
    # Logic: I will overwrite Caddyfile.prod with a version that points to NEW_COLOR.
fi

# Prepare new Caddyfile content
# We replace placeholders with actual container names
sed "s/{{UPSTREAM_API}}/$NEW_COLOR-api-1/g; s/{{UPSTREAM_FRONTEND}}/$NEW_COLOR-frontend-1/g" "$TEMPLATE" > "$CADDYFILE_PROD"

# Reload Caddy (in infra project)
docker compose -p infra -f "$COMPOSE_GATEWAY" exec caddy caddy reload

echo "--- Traffic Switched ---"

# 5. Cleanup Old Color
if [ -n "$CURRENT_COLOR" ]; then
    # Double check we are not killing the new color
    if [ "$CURRENT_COLOR" != "$NEW_COLOR" ]; then
        echo "--- Stopping Old Color ($CURRENT_COLOR) ---"
        docker compose -p "$CURRENT_COLOR" -f "$COMPOSE_APP" down
    fi
fi

echo "--- Deployment Complete ($NEW_COLOR Active) ---"
