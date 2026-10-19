# Enterprise Security Architecture, Secrets Management & Audit Logging

This document outlines authentication mechanisms, secrets handling, defense-in-depth measures, and immutable audit logging across the AI QA Platform.

---

## 1. Authentication Mechanisms

The AI QA Platform supports multi-tier authentication:
1. **Bearer Token Authentication**:
   - Sessions are HMAC-SHA256 signed with `APP_SECRET_KEY` and carry an expiry that is verified on every request; a tampered or expired token is rejected with 401.
   - The run-event SSE stream (whose browser client cannot send custom headers) additionally accepts the token as an `access_token` query parameter, and only on that route.
2. **Service API Keys (`aqp_live_*`)**:
   - SHA-256 hashed API tokens with prefix identifiers (e.g. `aqp_live_abc123...`) for CI/CD pipelines (Jenkins, GitHub Actions, GitLab CI).
   - Instant revocation, squad/role binding, and last-used tracking.

---

## 2. Secrets Management & Safe Masking

Integration credentials are supplied through environment variables (`GITHUB_TOKEN`, `JIRA_*`, `TESTRAIL_*`, `JENKINS_*`, `QA_AI_API_KEY`, `JEV_API_KEY`) and are never returned in plain text by the API.
- `SensitiveRedactor` masks tokens in failure artifacts, stack traces, and AI prompts/logs.
- `SecretStore` (encrypted at rest with `APP_SECRET_KEY`) is available for database-backed key storage with Fernet encryption.
- Secrets are strictly excluded from AI context selection, effective config inspection, and API responses.

---

## 3. Defense-in-Depth

- **Path Traversal Protection**: Workspace operations are strictly confined to authorized project root directories under `runtime/workspaces/<project_id>`. Any relative or symlinked escape attempts return HTTP 400.
- **SQL Injection Prevention**: Full parameterized query execution via SQLAlchemy 2.0 async ORM.
- **CORS & Origin Hardening**: Explicit origin whitelisting via configurable FastAPI middleware.

---

## 4. Immutable Security & Integration Audit Logging

The platform maintains two tamper-evident audit logs:

1. **Security Audit Log (`security_audits`)**:
   - Records all authentication attempts (login success/denial), user provisioning, role mutations, team memberships, and API key lifecycles.
   - Captures actor ID, actor email, target resource, IP address, status (`SUCCESS`, `DENIED`, `FAILED`), and structured metadata.

2. **Integration Audit Log (`integration_audits`)**:
   - Tracks all external write operations into Jira (bug creation, requirement imports) and TestRail (test result publishing).
   - Records external system, operation type, dry-run flag, target ticket/run IDs, and payload hashes.

### Retention & Querying
- **Security Endpoint**: `GET /api/audit/security` (supports filtering by `actor_id`, `action`, `limit`).
- **Integration Endpoint**: `GET /api/audit/integrations` (supports filtering by `system`, `limit`).
- **Database Indexing**: Indexed on `created_at`, `actor_id`, `action`, and `status` for rapid compliance investigations (SOC2 / ISO 27001).

---

## 5. Quality Discovery Boundary

Quality Discovery points a real Chromium browser at a user-supplied URL, so the exploration is itself a security boundary. See [QUALITY_DISCOVERY.md](QUALITY_DISCOVERY.md) §7 for the full model.

**Enforced:**
- **Host allowlist on two layers** — route guards inside the browser context (`restrict_navigation`: HTTP/HTTPS only, allowlisted host, credentials in URL rejected, WebSockets likewise) plus a pre-navigation check in the executor. The allowlist is the start-URL host ∪ run-level `allowed_domains` ∪ `discovery.allowed_domains`; entries with a scheme, path or single-label host are rejected at validation time.
- **No destructive actions by default** — `discovery.safe_mode: true`; cart/checkout/payment-style mutations are refused unless the run's requirement explicitly allows them.
- **Bounded execution** — `max_actions`, `max_failures`, `max_depth`, `max_states`, `max_runtime_minutes`, `max_candidates`, `max_screenshots`, `max_events`. No unattended outer loop.
- **Redaction** — sensitive values are masked before they reach an event, evidence bundle or the UI.
- **Artifact confinement** — evidence files must resolve inside the configured artifact root.
- **Project ACL** — every discovery route, including the live SSE stream, passes the same project access guard as the run (non-members get 404, not 403, so project existence is not probeable). The same guard covers the neighbouring project-scoped families: `/workspaces/{id}/git/*` and `/pr/*`, `/ai/requirements/{id}/*`, `/ai/test-designs/{id}/*`, `/test-designs/*`, `/lifecycle/projects/{id}/*`, `/onboarding/{id}/*` and `/runs/{id}/runtime`. Stored artifacts carry their own `project_id` and are resolved through the same guard (`/artifacts/{id}/info`, `/artifacts/{id}/download`, and `POST /artifacts/upload` when a project is named); an artifact with no project row is admin-only, which is deliberately stricter than the previous world-readable download. Worker/job endpoints stay role-only.

**Known gaps (open):** the allowlist matches host names only (no private-IP/link-local/CIDR blocking, no port restriction); a running exploration occupies one `TaskRuntimeService` worker slot for its whole duration.
