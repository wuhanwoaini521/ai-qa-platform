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
        │  PostgreSQL  │           │ Artifact Store │         │ Distributed   │
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

---

## 2. Environment Configuration Reference

Key variables to configure in `.env`:

| Variable | Description | Production Recommended Value |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy async connection string | `postgresql+asyncpg://user:pass@host:5432/db` |
| `AI_QA_AUTH_TOKEN` | Bearer token a distributed worker presents to the API | an API key created in the UI |
| `AUTH_REQUIRED` | Require a bearer token on every non-probe route | `true` |
| `APP_SECRET_KEY` | HMAC secret used to sign session tokens and encrypt stored secrets | 64-char random hex (`openssl rand -hex 32`) |
| `QA_AI_ENABLED`, `QA_AI_PROVIDER`, `QA_AI_API_KEY`, `QA_AI_BASE_URL`, `QA_AI_MODEL`, `QA_AI_TIMEOUT_SECONDS`, `QA_AI_MAX_RETRIES` | AI provider enablement, endpoint, model and request policy (environment overrides YAML) | Defaults match `config/config.yaml`; supply the provider key securely |
| `JEV_ENABLED`, `JEV_API_KEY`, `JEV_BASE_URL`, `JEV_MODEL`, `JEV_TIMEOUT_SECONDS`, `JEV_RETRIES`, `JEV_MINIMUM_CONFIDENCE` | Jev decision provider policy (environment overrides YAML) | Defaults match `config/config.yaml`; supply the Jev key securely |
| `GITHUB_TOKEN`, `JIRA_*`, `TESTRAIL_*`, `JENKINS_*` | Integration credentials (each integration falls back to a dry-run adapter when unset) | optional |
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

## 5. Verifying a release candidate without pushing (Round 20)

CI runs on push to `main` only, so a release candidate built overnight has no CI badge. The reproducible
substitute is to run the exact CI commands plus the container drills below; the Round 20 evidence lives in
`.ai-runs/overnight-delivery/rounds/r20_ci_parity.md` and `rounds/r20-deploy.json`.

```bash
# 1. The same commands CI runs (backend, then the PostgreSQL channel)
uv run ruff check . && uv run ruff format --check .
uv run python scripts/export_openapi.py --check
uv run pytest -q
docker run -d --name aiqa-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=aiqa_test -p 55432:5432 postgres:16-alpine
AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/aiqa_test uv run pytest apps/api -q
pnpm --filter @ai-qa/web test && pnpm --filter @ai-qa/web typecheck && pnpm --filter @ai-qa/web lint && pnpm --filter @ai-qa/web build

# 2. Build and start an isolated stack on spare ports
docker compose -p aiqa-drill --env-file drill.env up -d --build postgres api web
curl -fsS http://127.0.0.1:8010/api/health/live && curl -fsS http://127.0.0.1:8010/api/health

# 3. Fail-fast check: the API must refuse to start without a secret key
docker run --rm -e DISABLE_APP_SECRET=1 <api-image> python -m app   # exits non-zero, says which setting is missing

# 4. Migrations against the containerised database, then tear down
docker compose -p aiqa-drill exec api alembic downgrade -1 && docker compose -p aiqa-drill exec api alembic upgrade head
docker compose -p aiqa-drill down -v
```

Two defects this drill found in the shipped Dockerfiles, both fixed: the API image declared
`HEALTHCHECK … CMD-SHELL`, which is a Compose keyword and made `docker build` fail with
`Unknown type "CMD-SHELL"`, and `stored_artifacts.created_by` was too narrow for the labels the recorder
stores (see `apps/api/alembic/versions/0021_artifact_actor_width.py`). PostgreSQL rejects that insert while
SQLite silently accepted it, so the PostgreSQL CI job is the check that catches this class of defect.
