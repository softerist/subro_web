# Base stage
FROM node:20-alpine as base
WORKDIR /app
COPY package*.json ./
# Install dependencies including devDependencies
RUN npm ci

# Development stage
FROM base as development
# Copy source code (though usually mounted via volume in dev)
COPY . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Build stage
FROM base as build
COPY . .
RUN npm run build

# Production stage
FROM nginx:stable-alpine as production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Support running as non-root
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html && \
        chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx/conf.d
RUN touch /var/run/nginx.pid && \
        chown -R nginx:nginx /var/run/nginx.pid

USER nginx
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
