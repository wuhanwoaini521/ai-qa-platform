# Enterprise Security Architecture & Secrets Management

## 1. Authentication Mechanisms

The AI QA Platform supports multi-tier authentication:
1. **Bearer Token Authentication**:
   - Sessions are HMAC-SHA256 signed with `APP_SECRET_KEY` and carry an expiry that is verified on
     every request; a tampered or expired token is rejected with 401.
   - The run-event SSE stream (whose browser client cannot send headers) additionally accepts the
     token as an `access_token` query parameter, and only on that route.
2. **Service API Keys (`aqp_live_*`)**:
   - SHA-256 hashed API tokens with prefix identifiers (e.g. `aqp_live_abc123...`) for CI/CD pipelines (Jenkins, GitHub Actions, GitLab CI).
   - Instant revocation and last-used tracking.

---

## 2. Secrets Management & Safe Masking

Integration credentials are supplied through environment variables (`GITHUB_TOKEN`, `JIRA_*`,
`TESTRAIL_*`, `JENKINS_*`) and are never returned by the API.
- `SensitiveRedactor` masks tokens in failure artifacts, stack traces and AI prompts/logs.
- `SecretStore` (encrypted at rest with `APP_SECRET_KEY`) exists in the codebase but is not yet wired
  into the integration adapters — do not rely on it as a credential store today.
- Secrets are excluded from AI context selection and from API responses by the redactor.

---

## 3. Defense-in-Depth

- **Path Traversal Protection**: Workspace operations are strictly confined to authorized project root directories.
- **SQL Injection Prevention**: Full parameterized query execution via SQLAlchemy 2.0 ORM.
- **CORS & Origin Hardening**: Explicit origin whitelisting via configurable FastAPI middleware.
