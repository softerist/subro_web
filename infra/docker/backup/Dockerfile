ARG BASE_IMAGE=alpine:3.19
FROM ${BASE_IMAGE} AS production

# Install tools
# postgresql16-client for pg_dump
# redis for redis-cli (if needed)
# age for encryption
# aws-cli for S3 upload
# bash for scripting
RUN apk add --no-cache \
    postgresql16-client \
    redis \
    age \
    aws-cli \
    bash \
    curl \
    gzip

# Create backup directory
# Add script
# Context is repo root
COPY infra/scripts/backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh

# Create and use non-root user for security
RUN adduser -D -u 1000 backup
USER backup

CMD ["sleep", "infinity"]
