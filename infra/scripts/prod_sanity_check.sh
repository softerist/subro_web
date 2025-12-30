#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/infra/.env.prod}"
if [ ! -f "$ENV_FILE" ]; then
  ENV_FILE="$ROOT_DIR/.env.prod"
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing env file: $ENV_FILE"
  exit 1
fi

API_BASE="${SANITY_API_BASE_URL:-}"
if [ -z "$API_BASE" ]; then
  API_BASE="$(rg -n '^VITE_API_BASE_URL=' "$ENV_FILE" | head -n 1 | cut -d '=' -f 2-)"
fi

if [ -z "$API_BASE" ]; then
  echo "VITE_API_BASE_URL not found in $ENV_FILE"
  exit 1
fi

API_BASE="${API_BASE%\"}"
API_BASE="${API_BASE#\"}"

ROOT_BASE="${API_BASE%/api/v1}"
if [ "$ROOT_BASE" = "$API_BASE" ]; then
  ROOT_BASE="${API_BASE%/api}"
fi

CURL_FLAGS=(-fsS)
if [ "${SANITY_INSECURE:-1}" = "1" ]; then
  CURL_FLAGS+=(-k)
fi

echo "Using API base: $API_BASE"
echo "Using root base: $ROOT_BASE"

curl "${CURL_FLAGS[@]}" "$ROOT_BASE/health" >/dev/null
echo "Health: ok"

curl "${CURL_FLAGS[@]}" "$API_BASE/healthz" >/dev/null
echo "Healthz: ok"

SETUP_STATUS="$(curl "${CURL_FLAGS[@]}" "$API_BASE/setup/status")"
echo "Setup status: $SETUP_STATUS"
if ! echo "$SETUP_STATUS" | rg -q '"setup_completed":true'; then
  echo "Setup is not completed."
  exit 1
fi

if [ -n "${SANITY_API_KEY:-}" ]; then
  FOLDER_PATH="${SANITY_FOLDER_PATH:-/mnt/sata0/Media}"
  JOB_PAYLOAD="{\"folder_path\":\"$FOLDER_PATH\",\"language\":\"en\"}"
  JOB_STATUS="$(curl "${CURL_FLAGS[@]}" -X POST "$API_BASE/jobs/" -H "X-API-Key: $SANITY_API_KEY" -H "Content-Type: application/json" -d "$JOB_PAYLOAD")"
  echo "Job create: $JOB_STATUS"
else
  echo "SANITY_API_KEY not set; skipping job create check."
fi
