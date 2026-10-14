# Multi-stage Dockerfile for AI QA Platform Distributed Worker Node
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
COPY packages/project-model ./packages/project-model
COPY packages/qa-core ./packages/qa-core
COPY packages/integrations ./packages/integrations
COPY packages/platform-config ./packages/platform-config
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY config ./config

RUN uv sync --frozen --no-dev --package worker

# Stage 2: Runtime with Playwright and browsers
FROM python:3.13-slim-bookworm AS runner

WORKDIR /app

# Install system dependencies for Playwright headless browsers and Git
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

# Copy virtual environment and code
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/apps/worker /app/apps/worker
COPY --from=builder /app/config /app/config

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/apps/worker:/app/packages/qa-core:/app/packages/project-model:/app/packages/integrations"

# Install Playwright browser binaries
RUN playwright install chromium firefox

CMD ["python", "-m", "worker.main"]
