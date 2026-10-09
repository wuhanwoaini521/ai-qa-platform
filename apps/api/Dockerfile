# Multi-stage Dockerfile for AI QA Platform Backend API Service
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace pyproject and dependency definitions
COPY pyproject.toml uv.lock ./
COPY packages/project-model ./packages/project-model
COPY packages/qa-core ./packages/qa-core
COPY packages/integrations ./packages/integrations
COPY packages/platform-config ./packages/platform-config
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY config ./config

# Install dependencies into virtualenv
RUN uv sync --frozen --no-dev --package api

# Stage 2: Minimal Production Runtime
FROM python:3.13-slim-bookworm AS runner

WORKDIR /app

# Install runtime system libraries (e.g. curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r aiqa && useradd -r -g aiqa -d /app aiqa

# Copy virtual environment and application code from builder
COPY --from=builder --chown=aiqa:aiqa /app/.venv /app/.venv
COPY --from=builder --chown=aiqa:aiqa /app/packages /app/packages
COPY --from=builder --chown=aiqa:aiqa /app/apps/api /app/apps/api
COPY --from=builder --chown=aiqa:aiqa /app/config /app/config
COPY --chown=aiqa:aiqa examples/quickstart /app/examples/quickstart

# The browser recorder runs a headless Chromium instance inside the API container.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN /app/.venv/bin/playwright install chromium && \
    chown -R aiqa:aiqa /ms-playwright

# Create runtime storage directories with proper permissions
RUN mkdir -p /app/runtime/workspaces /app/runtime/artifacts && \
    chown -R aiqa:aiqa /app/runtime

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/apps/api:/app/packages/qa-core:/app/packages/project-model:/app/packages/integrations"

USER aiqa

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD-SHELL curl -f "http://127.0.0.1:${API_PORT:-8000}/api/health/live" || exit 1

CMD ["python", "-m", "app"]
