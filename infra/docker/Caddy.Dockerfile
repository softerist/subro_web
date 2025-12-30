FROM caddy:2-alpine

# Install nss-tools to provide certutil, allowing Caddy to install its local CA
RUN apk add --no-cache nss-tools
