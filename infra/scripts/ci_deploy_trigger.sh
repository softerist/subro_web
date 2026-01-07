#!/bin/bash
set -a
[ -f "$1" ] && source "$1"
set +a

DEPLOY_SCRIPT="$2"
LOG_FILE="$3"

echo "Starting detached deployment: $DEPLOY_SCRIPT" > "$LOG_FILE"
echo "Environment file: $1" >> "$LOG_FILE"
date >> "$LOG_FILE"

# Execute the deployment script and append to log
if [ -f "$DEPLOY_SCRIPT" ]; then
    chmod +x "$DEPLOY_SCRIPT"
    "$DEPLOY_SCRIPT" >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    echo "Deployment finished with exit code $EXIT_CODE" >> "$LOG_FILE"
    exit $EXIT_CODE
else
    echo "Error: Deployment script $DEPLOY_SCRIPT not found!" >> "$LOG_FILE"
    exit 1
fi
