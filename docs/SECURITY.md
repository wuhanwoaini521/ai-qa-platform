# Enterprise Security Architecture & Secrets Management

## 1. Authentication Mechanisms

The AI QA Platform supports multi-tier authentication:
1. **Bearer Token Authentication**:
   - Cryptographically verifiable sessions for human web console sessions.
2. **Service API Keys (`aqp_live_*`)**:
   - SHA-256 hashed API tokens with prefix identifiers (e.g. `aqp_live_abc123...`) for CI/CD pipelines (Jenkins, GitHub Actions, GitLab CI).
   - Instant revocation and last-used tracking.

---

## 2. Secrets Management & Safe Masking

All external integration secrets (Jira API tokens, TestRail passwords, GitHub tokens, Jenkins credentials) are stored through `SecretStore`:
- Encrypted at rest using platform master keys (`APP_SECRET_KEY`).
- Masked in all public and administrative API responses (e.g. `ghp_***321`).
- Never written to plain log files or sent to client frontends.

---

## 3. Defense-in-Depth

- **Path Traversal Protection**: Workspace operations are strictly confined to authorized project root directories.
- **SQL Injection Prevention**: Full parameterized query execution via SQLAlchemy 2.0 ORM.
- **CORS & Origin Hardening**: Explicit origin whitelisting via configurable FastAPI middleware.
