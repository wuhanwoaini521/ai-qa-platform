# AI QA Platform — Production Deployment Guide

This guide covers deployment architectures, container orchestration, environment configuration, database setup, and reverse proxy guidelines for running the AI QA Platform in staging and production environments.

---

## Architecture Overview

The AI QA Platform production deployment consists of:

```
                  ┌──────────────────────┐
                  │    Internet / VPN    │
                  └──────────┬───────────┘
                             │ HTTPS (443)
                  ┌──────────▼───────────┐
                  │  Nginx / Traefik /   │
                  │     Cloud LB         │
                  └─────┬──────────┬─────┘
          HTTP / Static │          │ /api/ (Proxy & SSE)
          ┌─────────────▼─┐      ┌─▼──────────────┐
          │   Web SPA     │      │  FastAPI API   │
          │ (Nginx Alpine)│      │  (Python 3.13) │
          └───────────────┘      └─┬───────┬────┬─┘
                                   │       │    │
               ┌───────────────────┘       │    └────────────────────┐
               │                           │                         │
        ┌──────▼───────┐           ┌───────▼────────┐         ┌──────▼────────┐
        │  PostgreSQL  │           │  MinIO / S3    │         │ Distributed   │
        │  (Primary DB)│           │  (Artifacts)   │         │ Workers (xN)  │
        └──────────────┘           └────────────────┘         └───────────────┘
```

---

## 1. Quick Start: Docker Compose

The fastest way to deploy the complete platform is using the pre-configured `docker-compose.yml`:

```bash
# 1. Clone repository
git clone git@github.com:wuhanwoaini521/ai-qa-platform.git
cd ai-qa-platform

# 2. Copy and customize production environment
cp .env.example .env
vim .env

# 3. Launch stack with 2 distributed test runner nodes
./scripts/deploy.sh --build --scale-workers 2
```

The stack exposes:
- **Web Frontend**: `http://localhost:3000` (or `http://localhost:80`)
- **Backend API & Swagger Docs**: `http://localhost:8000/docs`
- **Prometheus Metrics**: `http://localhost:8000/api/metrics`
- **MinIO S3 Console**: `http://localhost:9001` (user: `minioadmin`, pass: `minioadmin`)

---

## 2. Environment Configuration Reference

Key variables to configure in `.env`:

| Variable | Description | Production Recommended Value |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy async connection string | `postgresql+asyncpg://user:pass@host:5432/db` |
| `SECURITY_JWT_SECRET` | Secret key for signing user auth tokens | 64+ char random hexadecimal string |
| `SECURITY_TOKEN_EXPIRE_MINUTES` | User session token lifetime | `1440` (24 hours) |
| `S3_ENDPOINT_URL` | Object storage endpoint | `http://minio:9000` or AWS S3 URL |
| `S3_BUCKET_NAME` | Bucket for storing test execution traces & artifacts | `ai-qa-artifacts` |
| `AI_PROVIDER` | Active LLM inference provider | `openai`, `anthropic`, `gemini`, or `mock` |
| `AI_MONTHLY_BUDGET_USD` | Monthly AI cost ceiling | `500.00` |
| `MAX_CONCURRENCY` | Maximum concurrent tests per worker node | `4` - `8` (based on CPU/RAM) |

---

## 3. Kubernetes / Helm Deployment Strategy

For cloud-native Kubernetes deployments:

1. **Stateful Services**:
   - Deploy PostgreSQL using Cloud SQL / RDS or Strimzi/Zalando operator.
   - Deploy S3 using AWS S3 / Google Cloud Storage.
2. **Stateless API Deployment**:
   - Horizontal Pod Autoscaler (HPA) targeting CPU 70%.
   - Readiness probe: `httpGet: /api/health/ready, port: 8000`.
   - Liveness probe: `httpGet: /api/health/live, port: 8000`.
3. **Distributed Worker Deployment**:
   - Scaled independently based on queue backlog (`ai_qa_jobs_status{state="queued"}`).
   - Dedicated node pool with high CPU/Memory for browser headless rendering.

---

## 4. SSL/TLS & Reverse Proxy Configuration

When hosting behind an enterprise reverse proxy (e.g. Nginx, Traefik, Caddy, Cloudflare):

### Crucial Reverse Proxy Settings:
- **Server-Sent Events (SSE)**: Ensure proxy buffering is explicitly disabled for `/api/runs/*/live` or `/api/` by setting `proxy_buffering off;` and `proxy_read_timeout 86400s;`.
- **Large Artifact Uploads**: Set `client_max_body_size 100M;` to support Playwright trace files and DOM video recordings.
