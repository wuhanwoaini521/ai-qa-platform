# Multi-stage Dockerfile for AI QA Platform Web Frontend

# Stage 1: Build Frontend Assets
FROM node:22-alpine AS builder

WORKDIR /app

# Enable Corepack and pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy root lockfile and package configs
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json ./apps/web/package.json

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy web source files
COPY apps/web ./apps/web

# Build static bundle
RUN pnpm --filter @ai-qa/web build

# Stage 2: Production Nginx Server
FROM nginx:alpine AS runner

# Remove default nginx static assets
RUN rm -rf /usr/share/nginx/html/*

# Copy built static assets from builder stage
COPY --from=builder /app/apps/web/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
