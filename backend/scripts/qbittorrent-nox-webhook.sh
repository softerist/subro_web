#!/bin/bash

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

# Load environment from repo root if available.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

# Environment variables (configured in .env):
# SUBRO_API_BASE_URL, SUBRO_API_KEY
# Optional: PLEX_BASE_URL, PLEX_TOKEN, PLEX_SECTION_IDS (comma-separated), PLEX_SECTION_TOKENS (comma-separated)
SUBRO_API_BASE_URL="${SUBRO_API_BASE_URL:-}"
SUBRO_API_KEY="${SUBRO_API_KEY:-}"
PLEX_BASE_URL="${PLEX_BASE_URL:-}"
PLEX_TOKEN="${PLEX_TOKEN:-}"
PLEX_SECTION_IDS="${PLEX_SECTION_IDS:-}"
PLEX_SECTION_TOKENS="${PLEX_SECTION_TOKENS:-}"

if [ -z "$SUBRO_API_BASE_URL" ] || [ -z "$SUBRO_API_KEY" ]; then
    echo "Error: SUBRO_API_BASE_URL and SUBRO_API_KEY must be set in the environment."
    exit 1
fi

API_JOBS_URL="${SUBRO_API_BASE_URL%/}/jobs/"

echo "Submitting job to API..."
# -s: Silent
# -L: Follow redirects
# -X POST: Submission method
RESPONSE=$(curl -sL -w "\nHTTP_STATUS:%{http_code}" -X POST "$API_JOBS_URL" \
  -H "X-API-Key: $SUBRO_API_KEY" \
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
