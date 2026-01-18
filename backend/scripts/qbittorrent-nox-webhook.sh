#!/bin/bash
# qBittorrent-nox Webhook Script
# Add this path to your qBittorrent-nox download post-completion execution:
# <path_to_app>/backend/scripts/qbittorrent-nox-webhook.sh "%F"
# Execution logs path: /opt/subro_web/logs/webhook.log
# Note: Use "%F" in qBittorrent to pass the Content Path.

## Normal operation
#  ./qbittorrent-nox-webhook.sh "/data/torrents/My.Movie"
#
## Dry run
#  DRY_RUN=true ./qbittorrent-nox-webhook.sh "/data/torrents/Test"
#
## JSON logging
#  JSON_LOGGING=true ./qbittorrent-nox-webhook.sh "/data/torrents/Movie"
#
## Health check
#  ./qbittorrent-nox-webhook.sh --health
#
## With notifications
#  NOTIFY_ON_FAILURE=true DISCORD_WEBHOOK_URL="https://..." ./qbittorrent-nox-webhook.sh "/data/torrents/Movie"
#
## Custom retry settings
#  MAX_API_RETRIES=5 RETRY_BASE_DELAY=3 ./qbittorrent-nox-webhook.sh "/data/torrents/Movie"

set -euo pipefail

umask 077

SCRIPT_VERSION="3.3.0"
SCRIPT_START_TIME="$(date +%s)"

# ============================================
# Configuration
# ============================================
LOG_DIR="${LOG_DIR:-/opt/subro_web/logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/webhook.log}"
MAX_LOG_SIZE="${MAX_LOG_SIZE:-10485760}"  # 10MB default
WEBHOOK_ENV_FILE="${WEBHOOK_ENV_FILE:-/opt/subro_web/secrets/.env.webhook}"
CONFIG_FILE="${CONFIG_FILE:-/etc/subro_webhook.conf}"

LOCK_DIR="${LOCK_DIR:-/tmp/subro_webhook}"
DRY_RUN="${DRY_RUN:-false}"
JSON_LOGGING="${JSON_LOGGING:-false}"

# Retry configuration
MAX_API_RETRIES="${MAX_API_RETRIES:-3}"
RETRY_BASE_DELAY="${RETRY_BASE_DELAY:-2}"  # Base delay for exponential backoff

# Notifications (optional)
NOTIFY_ON_FAILURE="${NOTIFY_ON_FAILURE:-false}"
DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"

# ============================================
# Helpers
# ============================================
now_ts() { date '+%Y-%m-%d %H:%M:%S'; }
now_iso() { date '+%Y-%m-%dT%H:%M:%S%z'; }

# JSON logging (optional)
log_json() {
  local level="$1"; shift
  local msg="$*"

  # jq required for JSON logging
  if ! command -v jq >/dev/null 2>&1; then
    # Fall back to text if jq not available
    printf "%s [%s] %s\n" "$(now_ts)" "$level" "$msg"
    return 0
  fi

  jq -n \
    --arg timestamp "$(now_iso)" \
    --arg level "$level" \
    --arg message "$msg" \
    --arg torrent_path "${TORRENT_PATH:-}" \
    --arg version "$SCRIPT_VERSION" \
    '{timestamp: $timestamp, level: $level, message: $message, torrent_path: $torrent_path, version: $version}'
}

log_line() {
  local level="$1"; shift
  if [ "$JSON_LOGGING" = "true" ]; then
    log_json "$level" "$@"
  else
    printf "%s [%s] %s\n" "$(now_ts)" "$level" "$*"
  fi
}

log_info()    { log_line "INFO"  "$@"; }
log_warning() { log_line "WARN"  "$@"; }
log_error()   { log_line "ERROR" "$@" >&2; }

show_help() {
  cat <<EOF
qBittorrent-nox Webhook Script v${SCRIPT_VERSION}

Usage:
  $0 <torrent_path>
  $0 -h|--help
  $0 --health

Environment variables:
  SUBRO_API_BASE_URL     Base URL for Subro API (must start with http:// or https://)
  SUBRO_API_KEY          Authentication key for webhook (or loaded from WEBHOOK_ENV_FILE)

  PLEX_BASE_URL          (Optional) Plex server URL
  PLEX_TOKEN             (Optional) Plex token (global)
  PLEX_SECTION_IDS       (Optional) Comma-separated library section IDs (default: 1,2)
  PLEX_SECTION_TOKENS    (Optional) Comma-separated tokens per section ID

  LOG_DIR                Log directory (default: /opt/subro_web/logs)
  LOG_FILE               Log file path (default: \$LOG_DIR/webhook.log)
  MAX_LOG_SIZE           Log rotation threshold in bytes (default: 10485760)
  WEBHOOK_ENV_FILE       Webhook env file (default: /opt/subro_web/secrets/.env.webhook)
  CONFIG_FILE            Optional config file (default: /etc/subro_webhook.conf)

  DRY_RUN                Set to "true" to avoid API/Plex calls
  JSON_LOGGING           Set to "true" for JSON log lines (requires jq)

  MAX_API_RETRIES        Maximum API retry attempts (default: 3)
  RETRY_BASE_DELAY       Base delay for exponential backoff in seconds (default: 2)

  NOTIFY_ON_FAILURE      Set to "true" to send notifications on failure
  DISCORD_WEBHOOK_URL    Discord webhook URL for notifications
  SLACK_WEBHOOK_URL      Slack webhook URL for notifications

Examples:
  $0 "/data/torrents/My.Torrent.Name"
  DRY_RUN=true $0 "/data/torrents/My.Torrent.Name"
  JSON_LOGGING=true $0 "/data/torrents/My.Torrent.Name"
  $0 --health  # Check if API is reachable
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log_error "'$cmd' is required but not installed."
    exit 1
  fi
}

hash_string() {
  # Portable-ish hashing for lock naming
  local s="$1"
  if command -v md5sum >/dev/null 2>&1; then
    printf "%s" "$s" | md5sum | awk '{print $1}'
  elif command -v md5 >/dev/null 2>&1; then
    printf "%s" "$s" | md5 -q
  elif command -v shasum >/dev/null 2>&1; then
    printf "%s" "$s" | shasum | awk '{print $1}'
  else
    printf "%s" "$s" | tr -c '[:alnum:]' '_' | cut -c1-64
  fi
}

# Send notification on failure
send_notification() {
  local message="$1"
  local title="${2:-Subro Webhook Failure}"

  if [ "$NOTIFY_ON_FAILURE" != "true" ]; then
    return 0
  fi

  # Discord notification
  if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    local payload
    payload=$(jq -n \
      --arg title "$title" \
      --arg desc "$message" \
      --arg ts "$(now_iso)" \
      '{embeds: [{title: $title, description: $desc, timestamp: $ts, color: 15158332}]}' 2>/dev/null || echo "")

    if [ -n "$payload" ]; then
      curl -s --max-time 10 -X POST "$DISCORD_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$payload" >/dev/null 2>&1 || true
    fi
  fi

  # Slack notification
  if [ -n "$SLACK_WEBHOOK_URL" ]; then
    local payload
    payload=$(jq -n \
      --arg text "$title: $message" \
      '{text: $text}' 2>/dev/null || echo "")

    if [ -n "$payload" ]; then
      curl -s --max-time 10 -X POST "$SLACK_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$payload" >/dev/null 2>&1 || true
    fi
  fi
}

# Track lock for cleanup
LOCK_FILE=""
LOCK_KIND=""

cleanup() {
  local exit_code=$?

  # Best-effort lock cleanup
  if [ -n "${LOCK_KIND:-}" ]; then
    if [ "$LOCK_KIND" = "mkdir" ] && [ -n "${LOCK_FILE:-}" ]; then
      rmdir "$LOCK_FILE" 2>/dev/null || true
    elif [ "$LOCK_KIND" = "flock" ]; then
      if [ -n "${LOCK_FILE:-}" ]; then
        rm -f "$LOCK_FILE" 2>/dev/null || true
      fi
    fi
  fi

  if [ $exit_code -ne 0 ]; then
    log_warning "Exiting with code $exit_code"
    send_notification "Script exited with error code $exit_code for path: ${TORRENT_PATH:-unknown}" "Webhook Error"
  fi
  exit $exit_code
}

trap cleanup EXIT
trap 'log_warning "Interrupted (INT/TERM). Cleaning up..."; exit 1' INT TERM

# ============================================
# Early argument handling
# ============================================
TORRENT_PATH=""
SUBRO_API_KEY_ARG=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      show_help
      exit 0
      ;;
    --health)
      # Run health check logic immediately then exit
      # (Use a function or block here to avoid duplication, but for now copying logic structure)
      echo "Running health check..."
      # Load minimal config for health check
      SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
      REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

      for file in "$CONFIG_FILE" "$REPO_ROOT/.env" "/opt/subro_web/.env"; do
        if [ -f "$file" ]; then
          set -o allexport
          # shellcheck disable=SC1090
          source "$file" 2>/dev/null || true
          set +o allexport
          break
        fi
      done

      if [ -f "$WEBHOOK_ENV_FILE" ]; then
        # shellcheck disable=SC1090
        source "$WEBHOOK_ENV_FILE" 2>/dev/null || true
      fi

      if [ -z "${SUBRO_API_BASE_URL:-}" ]; then
        echo "ERROR: SUBRO_API_BASE_URL not configured"
        exit 1
      fi

      echo "Checking API endpoint: $SUBRO_API_BASE_URL"
      http_code=$(curl -s --max-time 10 -o /dev/null -w "%{http_code}" "${SUBRO_API_BASE_URL%/}/" 2>&1 || echo "000")

      if [ "$http_code" = "000" ]; then
        echo "ERROR: Cannot connect to API"
        exit 1
      elif [ "$http_code" -ge 200 ] && [ "$http_code" -lt 500 ]; then
        echo "SUCCESS: API is reachable (HTTP $http_code)"
        exit 0
      else
        echo "WARNING: Unexpected response (HTTP $http_code)"
        exit 1
      fi
      shift
      ;;
    --api-key=*)
      SUBRO_API_KEY_ARG="${1#*=}"
      shift
      ;;
    --api-key)
      if [ -n "${2:-}" ]; then
        SUBRO_API_KEY_ARG="$2"
        shift 2
      else
        echo "ERROR: --api-key requires a value" >&2
        exit 1
      fi
      ;;
    -*)
      # Ignore other flags or error? Let's ignore unknown flags to be safe with future qBittorrent params
      log_warning "Unknown option: $1"
      shift
      ;;
    *)
      if [ -z "$TORRENT_PATH" ]; then
        TORRENT_PATH="$1"
      else
        # If we already have a path, this might be extra args from qBittorrent?
        # Just warn and ignore
        log_warning "Ignoring extra argument: $1"
      fi
      shift
      ;;
  esac
done

if [ -z "$TORRENT_PATH" ]; then
  echo "ERROR: No torrent path provided." >&2
  echo "Usage: $0 <torrent_path> [--api-key KEY]" >&2
  exit 1
fi

# ============================================
# Logging Setup (secure perms)
# ============================================
mkdir -p "$LOG_DIR"
chmod 775 "$LOG_DIR" 2>/dev/null || true
if [ ! -w "$LOG_DIR" ]; then
  echo "ERROR: Cannot write to log dir: $LOG_DIR" >&2
  exit 1
fi

touch "$LOG_FILE"
chmod 640 "$LOG_FILE" 2>/dev/null || true
if [ ! -w "$LOG_FILE" ]; then
  echo "ERROR: Cannot write to log file: $LOG_FILE" >&2
  exit 1
fi

# Log rotation with timestamp
if [ -f "$LOG_FILE" ]; then
  FILE_SIZE=$(
    stat -f%z "$LOG_FILE" 2>/dev/null \
      || stat -c%s "$LOG_FILE" 2>/dev/null \
      || echo 0
  )
  if [ "$FILE_SIZE" -gt "$MAX_LOG_SIZE" ]; then
    ts="$(date '+%Y%m%d_%H%M%S')"
    mv -f "$LOG_FILE" "${LOG_FILE}.${ts}" 2>/dev/null || true
    touch "$LOG_FILE" && chmod 640 "$LOG_FILE" 2>/dev/null || true
  fi
fi

exec >>"$LOG_FILE" 2>&1

log_info "==================================="
log_info "Script v${SCRIPT_VERSION} starting"
log_info "==================================="
log_info "Processing path: $TORRENT_PATH"

# ============================================
# Prerequisites
# ============================================
require_cmd curl

# ============================================
# Path Validation
# ============================================
if [ ! -d "$TORRENT_PATH" ] && [ ! -f "$TORRENT_PATH" ]; then
  log_error "Torrent path does not exist or is inaccessible: $TORRENT_PATH"
  exit 1
fi

if [ ! -r "$TORRENT_PATH" ]; then
  log_error "No read permission for path: $TORRENT_PATH"
  exit 1
fi

# ============================================
# Concurrency Handling (per-path lock)
# ============================================
mkdir -p "$LOCK_DIR"
chmod 770 "$LOCK_DIR" 2>/dev/null || true
if [ ! -w "$LOCK_DIR" ] && [ ! -d "$LOCK_DIR" ]; then
  log_error "Cannot create or write to lock dir: $LOCK_DIR"
  exit 1
fi

lock_hash="$(hash_string "$TORRENT_PATH")"
LOCK_FILE_PATH="$LOCK_DIR/${lock_hash}.lock"

if command -v flock >/dev/null 2>&1; then
  LOCK_KIND="flock"
  LOCK_FILE="$LOCK_FILE_PATH"
  exec 200>"$LOCK_FILE"
  if ! flock -n 200; then
    log_warning "Another instance is processing '$TORRENT_PATH', skipping"
    exit 0
  fi
else
  LOCK_KIND="mkdir"
  LOCK_FILE="$LOCK_FILE_PATH.d"
  if ! mkdir "$LOCK_FILE" 2>/dev/null; then
    log_warning "Lock exists for '$TORRENT_PATH', skipping"
    exit 0
  fi
fi

# ============================================
# Environment Loading
# ============================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

POSSIBLE_ENV_FILES=(
  "$CONFIG_FILE"
  "${ENV_FILE:-}"
  "$REPO_ROOT/.env"
  "/opt/subro_web/.env"
  "$HOME/subro_web/.env"
)

LOADED_ENV=""
for file in "${POSSIBLE_ENV_FILES[@]}"; do
  if [ -n "$file" ] && [ -f "$file" ]; then
    log_info "Loading environment from: $file"
    set -o allexport
    set +u
    # shellcheck disable=SC1090
    source "$file"
    set -u
    set +o allexport
    LOADED_ENV="$file"
    break
  fi
done

if [ -z "$LOADED_ENV" ]; then
  log_warning "No env/config file found. Using environment variables."
fi

# ============================================
# Dry Run Mode
# ============================================
if [ "$DRY_RUN" = "true" ]; then
  log_info "DRY RUN enabled."
  log_info "DRY RUN: Would submit '$TORRENT_PATH' to Subro API (if configured)"
  log_info "DRY RUN: Would refresh Plex (if configured)"
  exit 0
fi

# ============================================
# Environment Variable Validation
# ============================================
SUBRO_API_BASE_URL="${SUBRO_API_BASE_URL:-}"
if [ -z "$SUBRO_API_BASE_URL" ]; then
  log_error "SUBRO_API_BASE_URL is not set."
  log_error "Set it in /opt/subro_web/.env or as an environment variable."
  exit 1
fi

if [[ ! "$SUBRO_API_BASE_URL" =~ ^https?:// ]]; then
  log_error "SUBRO_API_BASE_URL must start with http:// or https:// (got: $SUBRO_API_BASE_URL)"
  exit 1
fi

# ============================================
# Webhook Secret Loading
# ============================================
# Priority: 1. Command line arg, 2. Environment variable, 3. Fetch from Subro API
if [ -n "$SUBRO_API_KEY_ARG" ]; then
  SUBRO_API_KEY="$SUBRO_API_KEY_ARG"
  log_info "Using SUBRO_API_KEY from command line argument."
elif [ -n "${SUBRO_API_KEY:-}" ]; then
  log_info "Using SUBRO_API_KEY from environment."
elif [ -f "$WEBHOOK_ENV_FILE" ]; then
  set +u
  # shellcheck disable=SC1090
  source "$WEBHOOK_ENV_FILE"
  set -u
  log_info "Webhook key loaded from: $WEBHOOK_ENV_FILE"
fi

# If still no key, fetch from Subro API (localhost-only endpoint)
if [ -z "${SUBRO_API_KEY:-}" ]; then
  log_info "Fetching API key from Subro API..."

  KEY_ENDPOINT="${SUBRO_API_BASE_URL%/}/settings/webhook-key/current-key"
  key_response=$(curl -s --max-time 10 "$KEY_ENDPOINT" 2>&1)

  if echo "$key_response" | grep -q '"key"'; then
    # Extract key using jq if available, otherwise use grep/sed
    if command -v jq >/dev/null 2>&1; then
      SUBRO_API_KEY=$(echo "$key_response" | jq -r '.key' 2>/dev/null)
    else
      SUBRO_API_KEY=$(echo "$key_response" | grep -o '"key":"[^"]*"' | sed 's/"key":"//;s/"$//')
    fi

    if [ -n "$SUBRO_API_KEY" ] && [ "$SUBRO_API_KEY" != "null" ]; then
      log_info "API key fetched successfully from Subro API"
    else
      log_error "Failed to parse API key from response"
      log_error "Response: $key_response"
      exit 1
    fi
  else
    log_error "Failed to fetch API key from Subro API"
    log_error "Endpoint: $KEY_ENDPOINT"
    log_error "Response: $key_response"
    log_error "Make sure you've configured qBittorrent integration in the Subro web UI."
    exit 1
  fi
fi

log_info "API Base URL: $SUBRO_API_BASE_URL"

# ============================================
# Path Translation (Host -> Container)
# ============================================
# When qBittorrent runs on the host but Subro runs in Docker,
# the paths may be different. Configure mappings in the env file:
#   PATH_MAP_SRC="/root/Downloads"
#   PATH_MAP_DST="/data/downloads"
PATH_MAP_SRC="${PATH_MAP_SRC:-/root/Downloads}"
PATH_MAP_DST="${PATH_MAP_DST:-/data/downloads}"

if [[ "$TORRENT_PATH" == "$PATH_MAP_SRC"* ]]; then
  ORIGINAL_PATH="$TORRENT_PATH"
  TORRENT_PATH="${TORRENT_PATH/$PATH_MAP_SRC/$PATH_MAP_DST}"
  log_info "Path translated: $ORIGINAL_PATH -> $TORRENT_PATH"
fi

# ============================================
# Function: Submit job to Subro API
# ============================================
submit_to_api() {
  local api_url="${SUBRO_API_BASE_URL%/}/jobs/webhook"
  local json_payload

  log_info ""
  log_info "--- Submitting to Subro API ---"
  log_info "Endpoint: $api_url"

  # Build JSON payload with proper escaping
  local log_level="${LOG_LEVEL:-INFO}"

  if command -v jq >/dev/null 2>&1; then
    json_payload="$(jq -n --arg path "$TORRENT_PATH" --arg level "$log_level" '{folder_path: $path, log_level: $level}')"
  else
    log_warning "'jq' not found; using sed fallback for JSON escaping."
    local escaped_path
    escaped_path="$(printf "%s" "$TORRENT_PATH" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    json_payload="{\"folder_path\":\"$escaped_path\",\"log_level\":\"$log_level\"}"
  fi

  log_info "Payload prepared (path not logged for security)."

  local attempt
  for ((attempt=1; attempt<=MAX_API_RETRIES; attempt++)); do
    if [ "$attempt" -gt 1 ]; then
      local delay=$((RETRY_BASE_DELAY ** (attempt - 1)))
      log_warning "Retry $attempt/$MAX_API_RETRIES for API submission (exponential backoff: ${delay}s)"
      sleep "$delay"
    fi

    # Create secure temp file for curl config
    local curl_config
    curl_config="$(mktemp)"

    cat > "$curl_config" <<EOF
header = "X-Webhook-Key: $SUBRO_API_KEY"
header = "Content-Type: application/json"
EOF

    local body_file http_status
    body_file="$(mktemp)"

    http_status="$(
      curl --connect-timeout 10 --max-time 30 -sS \
        -K "$curl_config" \
        -o "$body_file" -w "%{http_code}" \
        -X POST "$api_url" \
        -d "$json_payload" 2>&1 || echo ""
    )"

    # Cleanup curl config immediately
    rm -f "$curl_config" 2>/dev/null || true

    local body body_len
    body="$(cat "$body_file" 2>/dev/null || true)"
    rm -f "$body_file" 2>/dev/null || true
    body_len="${#body}"

    if [ -z "$http_status" ] || [ "$http_status" = "000" ]; then
      log_warning "Connection failed or no HTTP status returned."
      continue
    fi

    log_info "HTTP Status: $http_status"
    if [ "$body_len" -lt 1000 ]; then
      log_info "Response: $body"
    else
      log_info "Response: [${body_len} bytes, truncated]"
    fi

    if [ "$http_status" -ge 200 ] && [ "$http_status" -lt 300 ]; then
      log_info "SUCCESS: Job submitted successfully"
      return 0
    fi

    # Retry on rate limit or server errors
    if [ "$http_status" -eq 429 ] || [ "$http_status" -ge 500 ]; then
      continue
    fi

    # Don't retry on other 4xx
    log_error "API returned HTTP $http_status (not retrying)"
    return 1
  done

  log_error "API submission failed after $MAX_API_RETRIES attempts"
  return 1
}

# ============================================
# Function: Refresh Plex libraries
# ============================================
refresh_plex() {
  local plex_base="${PLEX_BASE_URL:-}"

  if [ -z "$plex_base" ]; then
    log_info ""
    log_info "--- Plex Refresh ---"
    log_info "SKIPPED: PLEX_BASE_URL not configured"
    return 0
  fi

  if [[ ! "$plex_base" =~ ^https?:// ]]; then
    log_error "PLEX_BASE_URL must start with http:// or https:// (got: $plex_base)"
    return 1
  fi

  local plex_token="${PLEX_TOKEN:-}"
  local plex_section_ids="${PLEX_SECTION_IDS:-}"
  local plex_section_tokens="${PLEX_SECTION_TOKENS:-}"

  if [ -z "$plex_token" ] && [ -z "$plex_section_tokens" ]; then
    log_error "PLEX_BASE_URL is set, but no PLEX_TOKEN or PLEX_SECTION_TOKENS configured."
    return 1
  fi

  log_info ""
  log_info "--- Refreshing Plex Libraries ---"

  local section_ids="${plex_section_ids:-1,2}"
  IFS=',' read -r -a sections <<<"$section_ids"

  local tokens_arr=()
  if [ -n "$plex_section_tokens" ]; then
    IFS=',' read -r -a tokens_arr <<<"$plex_section_tokens"
  fi

  local refreshed=0
  local failed=0

  local idx
  for idx in "${!sections[@]}"; do
    local section_id="${sections[$idx]//[[:space:]]/}"
    [ -z "$section_id" ] && continue

    local token="$plex_token"
    if [ -n "$plex_section_tokens" ] && [ -n "${tokens_arr[$idx]:-}" ]; then
      token="${tokens_arr[$idx]//[[:space:]]/}"
    fi

    if [ -z "$token" ]; then
      log_warning "Skipping section $section_id (no token configured)"
      continue
    fi

    printf "%s [INFO] Refreshing section %s... " "$(now_ts)" "$section_id"

    # Create secure temp file for Plex token
    local plex_config
    plex_config="$(mktemp)"

    cat > "$plex_config" <<EOF
header = "X-Plex-Token: $token"
EOF

    local http_code
    http_code="$(
      curl --connect-timeout 5 --max-time 15 -s \
        -K "$plex_config" \
        -o /dev/null -w "%{http_code}" \
        "${plex_base%/}/library/sections/${section_id}/refresh" 2>&1 || echo "000"
    )"

    rm -f "$plex_config" 2>/dev/null || true

    if [[ "$http_code" =~ ^[0-9]{3}$ ]] && [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
      echo "SUCCESS (HTTP $http_code)"
      ((refreshed++))
    else
      echo "FAILED (HTTP $http_code)"
      ((failed++))
    fi
  done

  log_info "Plex refresh complete: $refreshed succeeded, $failed failed"

  if [ "$failed" -gt 0 ] && [ "$refreshed" -eq 0 ]; then
    return 1
  fi
  return 0
}

# ============================================
# Main Execution
# ============================================
API_SUCCESS=false
PLEX_SUCCESS=false

if submit_to_api; then
  API_SUCCESS=true
fi

if refresh_plex; then
  PLEX_SUCCESS=true
fi

# ============================================
# Execution Summary
# ============================================
SCRIPT_END_TIME="$(date +%s)"
SCRIPT_DURATION="$((SCRIPT_END_TIME - SCRIPT_START_TIME))"

log_info ""
log_info "==================================="
log_info "EXECUTION SUMMARY"
log_info "==================================="
log_info "Timestamp:        $(now_ts)"
log_info "Torrent Path:     $TORRENT_PATH"
if $API_SUCCESS; then
  log_info "API Submission:   ✓ SUCCESS"
else
  log_info "API Submission:   ✗ FAILED"
fi
if $PLEX_SUCCESS; then
  log_info "Plex Refresh:     ✓ SUCCESS"
else
  log_info "Plex Refresh:     ○ SKIPPED/FAILED"
fi
log_info "Script duration:  ${SCRIPT_DURATION}s"
log_info "==================================="

# Exit success if API succeeded (primary objective)
if $API_SUCCESS; then
  exit 0
else
  exit 1
fi
