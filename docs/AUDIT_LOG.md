# Immutable Security & Integration Audit Logging

## 1. Audit Trail Architecture

The platform maintains two tamper-evident audit logs:

1. **Security Audit Log (`security_audits`)**:
   - Records all authentication attempts (login success/denial), user provisioning, role mutations, team memberships, and API key lifecycles.
   - Captures actor ID, actor email, target resource, IP address, status (`SUCCESS`, `DENIED`, `FAILED`), and structured metadata.

2. **Integration Audit Log (`integration_audits`)**:
   - Tracks all external write operations into Jira (bug creation, requirement imports) and TestRail (test result publishing).

---

## 2. Retention & Querying

- **API Endpoint**: `GET /api/audit/security` (supports filtering by `actor_id`, `action`, `limit`).
- **Integration Endpoint**: `GET /api/audit/integrations` (supports filtering by `system`, `limit`).
- **Database Indexing**: Indexed on `created_at`, `actor_id`, `action`, and `status` for rapid audit investigations and compliance reporting (SOC2 / ISO 27001).
