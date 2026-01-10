#!/bin/bash
# Add this path to your qBittorrent-nox download post-completion executioon
# <path_to_app>/backend/scripts/qbittorrent-nox-webhook.sh "F"

# Enhanced Logging
LOG_FILE="/opt/subro_web/logs/webhook.log"
# Ensure log directory exists
mkdir -p /opt/subro_web/logs
# Redirect stdout and stderr to log file
exec >> "$LOG_FILE" 2>&1

echo "--- $(date) ---"
echo "Arguments received: $@"

TORRENT_PATH="$1"

if [ -z "$TORRENT_PATH" ]; then
    echo "Error: No torrent path provided."
    exit 1
fi

echo "Processing path: $TORRENT_PATH"

# Determine script and repo directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Assuming script is in backend/scripts/
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Define potential env file locations
POSSIBLE_ENV_FILES=(
    "${ENV_FILE:-}"
    "$REPO_ROOT/.env"
    "/opt/subro_web/.env"
    "$HOME/subro_web/.env"
)

LOADED_ENV=""

for file in "${POSSIBLE_ENV_FILES[@]}"; do
    if [ -n "$file" ] && [ -f "$file" ]; then
        echo "Loading environment from: $file"
        # Use simple sourcing with allexport
        set -o allexport
        # shellcheck disable=SC1090
        source "$file"
        set +o allexport
        LOADED_ENV="$file"
        break
    fi
done

if [ -z "$LOADED_ENV" ]; then
    echo "Warning: No .env file found. Expecting variables in environment."
fi

# Environment variables (configured in .env):
# SUBRO_API_BASE_URL (required)
# Optional: PLEX_BASE_URL, PLEX_TOKEN, PLEX_SECTION_IDS (comma-separated), PLEX_SECTION_TOKENS (comma-separated)
SUBRO_API_BASE_URL="${SUBRO_API_BASE_URL:-}"
PLEX_BASE_URL="${PLEX_BASE_URL:-}"
PLEX_TOKEN="${PLEX_TOKEN:-}"
PLEX_SECTION_IDS="${PLEX_SECTION_IDS:-}"
PLEX_SECTION_TOKENS="${PLEX_SECTION_TOKENS:-}"

# Read webhook secret from auto-generated file (created by backend on startup)
WEBHOOK_SECRET_FILE="/opt/subro_web/secrets/webhook_secret.txt"
if [ -f "$WEBHOOK_SECRET_FILE" ]; then
    WEBHOOK_SECRET=$(cat "$WEBHOOK_SECRET_FILE")
    echo "Webhook secret loaded from file (starts with: ${WEBHOOK_SECRET:0:4}...)"
else
    # Fallback to legacy SUBRO_API_KEY if secret file doesn't exist (old deployments)
    WEBHOOK_SECRET="${SUBRO_API_KEY:-}"
    if [ -n "$WEBHOOK_SECRET" ]; then
        echo "Using legacy SUBRO_API_KEY from .env"
    else
        echo "Error: Webhook secret file not found and no SUBRO_API_KEY set."
        echo "       Expected file: $WEBHOOK_SECRET_FILE"
        echo "       Run a new deployment or ensure the API container has started."
        exit 1
    fi
fi

echo "SUBRO_API_BASE_URL: $SUBRO_API_BASE_URL"

if [ -z "$SUBRO_API_BASE_URL" ]; then
    echo "Error: SUBRO_API_BASE_URL must be set in the environment or .env file."
    exit 1
fi

# Use the dedicated webhook endpoint (doesn't require user auth)
API_WEBHOOK_URL="${SUBRO_API_BASE_URL%/}/jobs/webhook"

echo "Submitting job to API webhook endpoint..."
# -s: Silent
# -L: Follow redirects
# -X POST: Submission method
RESPONSE=$(curl -sL -w "\nHTTP_STATUS:%{http_code}" -X POST "$API_WEBHOOK_URL" \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d "{\"folder_path\": \"$TORRENT_PATH\", \"log_level\": \"INFO\"}")

echo "API Response: $RESPONSE"
echo "qBittorrent-nox Webhook execution completed."

# Command 2: Refresh Plex libraries
if [ -n "$PLEX_BASE_URL" ]; then
    if [ -z "$PLEX_TOKEN" ] && [ -z "$PLEX_SECTION_TOKENS" ]; then
        echo "Error: PLEX_TOKEN or PLEX_SECTION_TOKENS must be set when PLEX_BASE_URL is provided."
        exit 1
    fi

    if [ -z "$PLEX_SECTION_IDS" ]; then
        PLEX_SECTION_IDS="1,2"
    fi

    IFS=',' read -r -a plex_sections <<< "$PLEX_SECTION_IDS"
    if [ -n "$PLEX_SECTION_TOKENS" ]; then
        IFS=',' read -r -a plex_tokens <<< "$PLEX_SECTION_TOKENS"
    fi

    for idx in "${!plex_sections[@]}"; do
        section_id="${plex_sections[$idx]//[[:space:]]/}"
        if [ -n "$section_id" ]; then
            token="$PLEX_TOKEN"
            if [ -n "$PLEX_SECTION_TOKENS" ] && [ -n "${plex_tokens[$idx]:-}" ]; then
                token="${plex_tokens[$idx]//[[:space:]]/}"
            fi

            if [ -z "$token" ]; then
                echo "Skipping Plex Section $section_id; no token configured."
                continue
            fi

            echo "Refreshing Plex Section $section_id..."
            curl -sL "${PLEX_BASE_URL%/}/library/sections/${section_id}/refresh?X-Plex-Token=${token}"
        fi
    done

    echo "Plex Webhook execution completed."
else
    echo "PLEX_BASE_URL not set; skipping Plex refresh."
fi
