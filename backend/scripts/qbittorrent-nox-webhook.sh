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

# Deduplicate path if it ends with same folder name twice (common with %R/%N)
# Example: /mnt/media/Show/Show -> /mnt/media/Show
BASENAME=$(basename "$TORRENT_PATH")
PARENT=$(dirname "$TORRENT_PATH")
PARENT_BASENAME=$(basename "$PARENT")

if [ "$BASENAME" == "$PARENT_BASENAME" ] && [ -d "$PARENT" ]; then
    echo "Duplicate path detected. Deduplicating: $TORRENT_PATH -> $PARENT"
    TORRENT_PATH="$PARENT"
fi
echo "Submitting job to API..."
# -s: Silent
# -L: Follow redirects
# -X POST: Submission method
RESPONSE=$(curl -sL -w "\nHTTP_STATUS:%{http_code}" -X POST https://secure.go.ro/api/v1/jobs/ \
  -H "X-API-Key: 71iLDlxlzSGUKKRmcGSoDJB9KieoTZm-mwfaPPpiUwI" \
  -H "Content-Type: application/json" \
  -d "{\"folder_path\": \"$TORRENT_PATH\", \"log_level\": \"INFO\"}")

echo "API Response: $RESPONSE"
echo "qBittorrent-nox Webhook execution completed."

# Command 2: Refresh Plex libraries
echo "Refreshing Plex Section 1..."
curl -sL "https://192-168-1-253.a5c879ccb59b49a89fe199e0adfcf932.plex.direct:32400/library/sections/1/refresh?X-Plex-Token=6cd07688-361f-4956-9bc1-2231189ed413"
echo "Refreshing Plex Section 2..."
curl -sL "https://192-168-1-253.a5c879ccb59b49a89fe199e0adfcf932.plex.direct:32400/library/sections/2/refresh?X-Plex-Token=5205257c-8868-48f1-a1ed-01e6c11244f9"
echo "Plex Webhook execution completed."
