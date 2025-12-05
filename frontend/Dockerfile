# VoxBridge Frontend - Production Build
# Multi-stage build for optimized production image

# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies (including devDependencies for build)
RUN npm ci

# Copy source code
COPY . .

# Build arguments for environment variables (injected at build time)
# VITE_WS_URL intentionally omitted - detected dynamically from window.location
ARG VITE_API_URL=

# Export as environment variables for Vite build
ENV VITE_API_URL=${VITE_API_URL}

# Build production bundle (now with env vars injected)
RUN npm run build

# Stage 2: Production server with nginx
FROM nginx:alpine

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -sf http://localhost/health > /dev/null || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
