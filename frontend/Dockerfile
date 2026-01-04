# Base stage
FROM node:20-alpine AS base
WORKDIR /app
COPY package*.json ./
# Install dependencies including devDependencies
RUN apk add --no-cache curl && npm ci

# Development stage
FROM base AS development
# Copy source code (though usually mounted via volume in dev)
COPY . .
USER node
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Build stage
FROM base AS build
COPY . .

# Accept build args for Vite environment variables
ARG VITE_API_BASE_URL
ARG VITE_WS_BASE_URL
ARG VITE_SETUP_TOKEN

# Set as environment variables for the build process
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_WS_BASE_URL=${VITE_WS_BASE_URL}
ENV VITE_SETUP_TOKEN=${VITE_SETUP_TOKEN}

RUN npm run build

# Production stage
FROM nginx:stable-alpine AS production
RUN apk add --no-cache curl
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.main.conf /etc/nginx/nginx.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Support running as non-root
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html && \
        chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx/conf.d

USER nginx
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
