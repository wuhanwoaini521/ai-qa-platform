# Role-Based Access Control (RBAC) Specification

## 1. User Roles

The platform enforces four hierarchical and capability-defined roles:

| Role | Description | Core Capabilities |
|---|---|---|
| **ADMIN** | Platform Superuser & Security Administrator | Full platform control, User management, Team assignment, API Key lifecycle, Security audits, Global settings |
| **QA_LEAD** | QA Lead & Release Gatekeeper | Test authoring, Execution, Jira/TestRail publishing, Release Gate approvals, Team management |
| **QA_ENGINEER** | Test Automation Engineer | Test Case creation, Automation Studio editing, Local/Jenkins test execution |
| **VIEWER** | Stakeholder / Product Manager | Read-only inspection of reports, runs, coverage, and release gates |

---

## 2. Granular Permissions Matrix

| Permission Key | Description | ADMIN | QA_LEAD | QA_ENGINEER | VIEWER |
|---|---|:---:|:---:|:---:|:---:|
| `project:read` | View project metadata, tests, and runs | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| `project:write` | Create / edit / delete projects | :white_check_mark: | :white_check_mark: | :x: | :x: |
| `requirement:write`| Create / edit / import Jira requirements | :white_check_mark: | :white_check_mark: | :white_check_mark: | :x: |
| `test_case:write` | Design and author test cases | :white_check_mark: | :white_check_mark: | :white_check_mark: | :x: |
| `automation:edit` | Generate & edit test scripts in Monaco | :white_check_mark: | :white_check_mark: | :white_check_mark: | :x: |
| `run:execute` | Launch test execution suites | :white_check_mark: | :white_check_mark: | :white_check_mark: | :x: |
| `release:gate` | Evaluate and approve release gates | :white_check_mark: | :white_check_mark: | :x: | :x: |
| `integration:manage`| Configure Jira, TestRail, Jenkins endpoints | :white_check_mark: | :white_check_mark: | :x: | :x: |
| `security:admin` | Manage users, roles, and view audit trail | :white_check_mark: | :x: | :x: | :x: |

---

## 3. Team & Squad Organization

Users can be organized into squads (e.g., *Frontend QA Squad*, *Payments Automation Squad*) with assigned squad roles (`LEAD`, `MEMBER`) for domain test ownership.

---

## 4. Enforcement

Roles are enforced centrally, not per router. `apps/api/app/api/authz.py` declares one policy table
(`RULES`, most specific prefix first) and a single application-level dependency
(`authorize_request`, installed in `apps/api/app/main.py`) resolves the caller and checks the
required permission for every non-public request.

- **Public paths**: `/api/health*`, `/api/metrics`, `/api/auth/login` and the interactive docs. These
  must stay reachable so container probes and the login round-trip work before any session exists.
- **Authentication**: `Authorization: Bearer <token>` where the token is either the login token or an
  API key (`aqp_live_...`). A missing or invalid credential is `401`.
- **Authorization**: a valid credential without the required permission is `403`. The guard runs
  *before* the route handler, so an unauthorised caller cannot reach any handler logic — including
  with a valid-looking but non-existent resource id.
- **Cluster infrastructure**: writes to `/api/workers` and `/api/jobs` require `security:admin`.
  Workers submit authoritative execution results and must use an ADMIN-owned service credential in
  `AI_QA_AUTH_TOKEN`. Existing Worker keys owned by QA_LEAD or QA_ENGINEER must be replaced by an
  administrator before restarting those workers; they now receive `403`. Reads require `project:read`.
  API keys currently inherit their owner's permissions; dedicated worker-only credential scopes are
  not implemented. Keep this credential on trusted worker hosts. Artifact reads require `project:read`;
  artifact writes require `automation:edit`.
- **Job completion**: workers submit real suite results through `/api/jobs/{id}/result`. The legacy
  `/complete` notification only acknowledges an already completed job; it cannot skip result persistence.
- **Unknown route families** fall back to `project:read` / `project:write` rather than to "no
  authentication", so a newly added router cannot silently become an open endpoint.

`AUTH_REQUIRED=false` is a development-only escape hatch: the API then treats every request as the
seeded administrator. It is documented in `.env.example`, defaults to `true`, and is exercised by
`apps/api/tests/test_authorization_rbac.py` (35 tests covering 401/403 denial paths, role
separation and the policy table itself).
