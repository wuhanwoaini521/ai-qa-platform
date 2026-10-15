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
