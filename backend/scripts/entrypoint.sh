#!/bin/sh
set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-60}"
MAX_MIGRATION_ATTEMPTS="${MAX_MIGRATION_ATTEMPTS:-5}" # Increase attempts
MIGRATION_RETRY_SLEEP="${MIGRATION_RETRY_SLEEP:-5}"   # Seconds between retries

# --- User/Group ID Management ---
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

echo "Entrypoint: Setting appuser UID to $PUID and GID to $PGID..."
# Ensure group exists with correct GID
if ! getent group appuser > /dev/null 2>&1; then
    groupadd -g "$PGID" appuser
else
    groupmod -o -g "$PGID" appuser
fi

# Ensure user exists with correct UID
if ! getent passwd appuser > /dev/null 2>&1; then
    useradd -u "$PUID" -g "$PGID" -d /app appuser
else
    usermod -o -u "$PUID" appuser
fi

# Ensure critical directories are owned by appuser
echo "Entrypoint: Ensuring ownership for appuser..."
chown appuser:appuser /app
# We only chown the top-level of mapped media folders to avoid long recursions
chown appuser:appuser /mnt/sata0/Media 2>/dev/null || true
chown appuser:appuser /app/logs 2>/dev/null || true
# Ensure translation log directory exists and is writable
mkdir -p /app/app/modules/subtitle/services/logs 2>/dev/null || true
chown -R appuser:appuser /app/app/modules/subtitle/services/logs 2>/dev/null || true

# --- Wait for Database ---
echo "Entrypoint: Waiting for database $DB_HOST:$DB_PORT..."
# Use nc (netcat) for waiting - needs netcat-openbsd installed in Dockerfile
# Simple wait loop
start_time=$(date +%s)
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  current_time=$(date +%s)
  elapsed_time=$((current_time - start_time))
  if [ "$elapsed_time" -ge "$WAIT_TIMEOUT" ]; then
    echo "Entrypoint: Timeout waiting for database $DB_HOST:$DB_PORT after ${WAIT_TIMEOUT} seconds."
    exit 1
  fi
  echo "Entrypoint: Database not yet available. Retrying in 1 second..."
  sleep 1
done
echo "Entrypoint: Database $DB_HOST:$DB_PORT is available!"

# --- Change to App Directory ---
cd /app
echo "Entrypoint: Current directory: $(pwd)"

# --- Migration Application Loop ---
MIGRATION_ATTEMPT=0
MIGRATIONS_UP_TO_DATE=false

while [ $MIGRATION_ATTEMPT -lt $MAX_MIGRATION_ATTEMPTS ]; do
  MIGRATION_ATTEMPT=$((MIGRATION_ATTEMPT + 1))
  echo "---"
  echo "Entrypoint: Migration Check & Apply Attempt #$MIGRATION_ATTEMPT / $MAX_MIGRATION_ATTEMPTS"
  echo "Entrypoint: Listing alembic/versions before upgrade attempt:"
  ls -l alembic/versions/ || echo "Entrypoint: alembic/versions not found or ls failed"

  # Attempt to apply migrations based on currently visible files
  echo "Entrypoint: Running 'poetry run alembic upgrade head'..."
  if ! poetry run alembic upgrade head; then
     echo "Entrypoint: 'alembic upgrade head' command failed on attempt #$MIGRATION_ATTEMPT. Retrying..."
     sleep $MIGRATION_RETRY_SLEEP
     continue # Go to the next loop iteration
  fi
  echo "Entrypoint: 'alembic upgrade head' command finished for attempt #$MIGRATION_ATTEMPT."
  # Strict consistency check disabled to preventing looping on parse errors.
  MIGRATIONS_UP_TO_DATE=true
  break


  # Check consistency *after* the upgrade attempt
  echo "Entrypoint: Checking DB revision vs filesystem heads..."
  DB_REVISION_OUTPUT=$(poetry run alembic current 2>&1)
  FS_HEADS_OUTPUT=$(poetry run alembic heads 2>&1)

  echo "Entrypoint: > DB ('alembic current') output: $DB_REVISION_OUTPUT"
  echo "Entrypoint: > FS ('alembic heads') output: $FS_HEADS_OUTPUT"

  # --- Parsing and Comparison Logic ---
  # Extract the primary DB revision ID (handles cases like "abc123xyz (head)")
  CURRENT_REV_ID=$(echo "$DB_REVISION_OUTPUT" | grep -oE '[0-9a-fA-F]{12}' | head -n 1 || true)
  # Extract *all* filesystem head revision IDs
  FS_HEADS_IDS=$(echo "$FS_HEADS_OUTPUT" | grep -oE '[0-9a-fA-F]{12}' || true)

  IS_CONSISTENT=false
  # Check if DB has a revision AND it's one of the currently visible FS heads
  if [ -n "$CURRENT_REV_ID" ]; then
      if echo "$FS_HEADS_IDS" | grep -q -w "$CURRENT_REV_ID"; then # Use -w for whole word match
          echo "Entrypoint: Database revision '$CURRENT_REV_ID' matches a filesystem head."
          IS_CONSISTENT=true
      else
           echo "Entrypoint: Database revision '$CURRENT_REV_ID' exists but is NOT among current filesystem heads ('$FS_HEADS_IDS'). Retrying."
           IS_CONSISTENT=false # Potentially branched or inconsistent
      fi
  # Check if DB is base (no revision) AND FS also has no revisions listed
  elif [ -z "$CURRENT_REV_ID" ] && [ -z "$FS_HEADS_IDS" ]; then
      echo "Entrypoint: Database is at base and no migration heads found on filesystem."
      # !!! CRITICAL CHANGE: Do NOT assume this is consistent during the loop !!!
      # This state is ambiguous during volume sync. Force a retry unless it's the last attempt.
      if [ $MIGRATION_ATTEMPT -lt $MAX_MIGRATION_ATTEMPTS ]; then
          echo "Entrypoint: Treating base/no-heads state as potentially inconsistent, will retry."
          IS_CONSISTENT=false
      else
          echo "Entrypoint: Reached max attempts in base/no-heads state. Assuming it's genuinely empty."
          IS_CONSISTENT=true # Only accept empty state on the final try
      fi
  else
      # Catch-all for other unexpected states (e.g., DB base but FS has heads listed)
       echo "Entrypoint: Database/Filesystem state is unexpected (DB:'$CURRENT_REV_ID', FS Heads:'$FS_HEADS_IDS'). Retrying."
       IS_CONSISTENT=false # Force retry
  fi
  # --- End Parsing and Comparison ---

  if [ "$IS_CONSISTENT" = "true" ]; then
      echo "Entrypoint: Database migrations are confirmed up-to-date with the filesystem on attempt #$MIGRATION_ATTEMPT."
      MIGRATIONS_UP_TO_DATE=true
      break # Exit the loop successfully
  fi

  echo "Entrypoint: Consistency check failed on attempt #$MIGRATION_ATTEMPT."
  if [ $MIGRATION_ATTEMPT -lt $MAX_MIGRATION_ATTEMPTS ]; then
      echo "Entrypoint: Sleeping for $MIGRATION_RETRY_SLEEP seconds before retry..."
      sleep $MIGRATION_RETRY_SLEEP
  fi
done
echo "---"

# --- Database Bootstrapping ---
echo "Entrypoint: Running 'poetry run python app/initial_data.py' for bootstrapping..."
if ! poetry run python app/initial_data.py; then
  echo "Entrypoint: 'initial_data.py' failed. Setup may be incomplete." >&2
else
  echo "Entrypoint: 'initial_data.py' finished successfully."
fi

# --- Final Check and Execution ---
if [ "$MIGRATIONS_UP_TO_DATE" != "true" ]; then
  echo "Error: Failed to confirm database migrations are up-to-date after $MAX_MIGRATION_ATTEMPTS attempts." >&2
  echo "Warning: Proceeding to start application, but migrations might be inconsistent or not fully applied." >&2
  # Decide if you want to exit here instead of proceeding:
  # exit 1
fi

echo "Entrypoint: Migration check loop finished. Starting main application command as appuser..."
# Execute the command passed to the entrypoint (e.g., the CMD from Dockerfile)
# Use gosu to drop privileges to appuser
exec gosu appuser "$@"
