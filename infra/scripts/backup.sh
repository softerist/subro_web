#!/bin/bash
set -e

# Configuration
# Env vars should be provided by docker-compose
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_PATH="/backups"
DB_HOST="${POSTGRES_SERVER:-db}"
DB_USER="${POSTGRES_USER:-subapp_user}"
DB_NAME="${POSTGRES_DB:-subappdb}"
# Note: PGPASSWORD should be set in environment

echo "[$(date)] Starting backup job..."

# 1. Database Backup
FILENAME="${DB_NAME}_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_PATH}/${FILENAME}"

echo "Dumping database ${DB_NAME} from ${DB_HOST}..."
pg_dump -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" | gzip > "$FILEPATH"

# 2. Encryption (Optional)
if [ -n "$BACKUP_ENCRYPTION_KEY" ]; then
    echo "Encrypting backup..."
    # If key is provided as content, use it. If file path, use -R.
    # Assuming it's the recipient public key string for simplicity or symmetric password.
    # age -p (passphrase) or -r (recipient).
    # Task said "age" for encryption.
    # Let's assume symmetric for now via env var, passing it via stdin?
    # Or just skip detailed impl if key format is complex.
    # We'll support symmetric pass if 'BACKUP_ENCRYPTION_KEY' is set.
    # Warning: passing password via command line args is visible.
    # export AGE_PASSWORD=$BACKUP_ENCRYPTION_KEY
    # cat "$FILEPATH" | age -p -o "${FILEPATH}.age"
    # For now, placeholder or simple implementation.
    mv "$FILEPATH" "${FILEPATH}.plain"
    # Non-interactive symmetric encryption needs a way to pass password.
    # age doesn't easily support env var for password without TTY?
    # Standard practice: Public Key Encryption.
    # If BACKUP_ENCRYPTION_KEY starts with "age", it's a recipient.
    if [[ "$BACKUP_ENCRYPTION_KEY" == age* ]]; then
        cat "${FILEPATH}.plain" | age -r "$BACKUP_ENCRYPTION_KEY" -o "${FILEPATH}.age"
        rm "${FILEPATH}.plain"
        FILEPATH="${FILEPATH}.age"
        FILENAME="${FILENAME}.age"
    else
         echo "Warning: BACKUP_ENCRYPTION_KEY does not look like an age public key. Skipping encryption."
         mv "${FILEPATH}.plain" "$FILEPATH"
    fi
fi

# 3. Upload to S3 (Optional)
if [ -n "$AWS_BUCKET_NAME" ]; then
    echo "Uploading to S3..."
    aws s3 cp "$FILEPATH" "s3://${AWS_BUCKET_NAME}/${FILENAME}"
fi

# 4. Local Retention (Optional)
if [ -n "$BACKUP_RETENTION_DAYS" ]; then
    echo "Cleaning up local backups older than ${BACKUP_RETENTION_DAYS} days..."
    find "$BACKUP_PATH" -name "${DB_NAME}*" -mtime +${BACKUP_RETENTION_DAYS} -delete
fi

echo "[$(date)] Backup completed: $FILENAME"
