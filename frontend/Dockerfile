# frontend/Dockerfile

# --- Base Stage ---
# Use an official Node.js LTS version
FROM node:22-alpine AS base

# Set working directory
WORKDIR /app

# Set PYTHONPATH environment variable
ENV PYTHONPATH=/app

# --- Dependencies Stage ---
# Install dependencies separately for better caching
FROM base AS dependencies

# Copy package definition files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci --omit=dev

# --- Development Stage ---
FROM node:lts-alpine AS development

# Install curl for healthcheck
RUN apk add --no-cache curl

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy the rest of the application code
COPY . .

EXPOSE 5173

# Default command might be overridden by compose, but good to have a default
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- Builder Stage ---
# Build the production version of the application
FROM dependencies AS builder

# Install dev dependencies needed for build
RUN npm install

# Copy the entire application source code
COPY . .

# Run the build command
RUN npm run build

# --- Production Stage ---
# Serve the static files using Nginx
FROM nginx:1.25-alpine AS production

# Copy nginx configuration file
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf

# Remove default Nginx welcome page
RUN rm /usr/share/nginx/html/*

# Copy the built static assets from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Start Nginx server
CMD ["nginx", "-g", "daemon off;"]
