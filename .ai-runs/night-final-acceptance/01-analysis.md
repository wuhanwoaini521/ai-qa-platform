# Initial Analysis — Night Final Acceptance

## Starting state

The task branch `agent/night-final-acceptance` was created from `main` at `567ab83` to isolate future acceptance commits while preserving inherited changes. The worktree had a substantial set of tracked modifications and untracked OpenAPI/test/run-log artifacts before this run; none were reset, cleaned, or staged. `mise.toml` is inherited and explicitly out of scope.

## Architecture and boundaries

- `apps/web`: React + TypeScript + Vite frontend.
- `apps/api`: FastAPI domain services, REST/SSE and database persistence.
- `apps/worker`: separate long-running worker package; no worker process was observed at initial inspection.
- `packages/qa-core`, `packages/project-model`, and adapters provide the shared testing/provider/browser contracts.
- Failure analysis uses the existing `FailureWorkflowService`, DecisionService/Jev boundary, `TestRunService`, and `BrowserRuntime`; no second Agent/Provider/Runtime is in scope.
- Human approval remains mandatory before repair Apply/source writes. Live acceptance tests must stop at proposal/approval state.

## Initial environment evidence

- Existing API on `127.0.0.1:8001` and Vite on `127.0.0.1:5174` are long-running inherited services; reuse only for read-only health/provider checks. Do not stop them.
- `/api/health/live`, `/api/health/ready`, and `/api/health` returned 200; readiness reported database and storage healthy.
- The configured DB is local SQLite. The test PostgreSQL URL and `docker`, `psql`, and `pg_isready` are unavailable; PostgreSQL validation is initially blocked.
- Effective config has real AI and Jev providers enabled and keys configured, with fallback disallowed. Secret values are not recorded. Actual provider availability and workflow acceptance remain unverified until live probes/tests run.
- Worker configuration points to Compose service `api` and has no worker auth token configured; no separate worker process was observed. Local API runner tests remain possible, but remote worker acceptance is not yet established.
- `AI_QA_TEST_DATABASE_URL` and live-acceptance flags were unset in the initial shell. `.env` is present and was loaded by the app's config manager; its contents are never copied into evidence.
- A long-lived local HTTP demo server on port 8765 and a child `multiprocessing` process under the existing API were observed. Their purpose/liveness will be checked before deciding whether they are task residue. Do not terminate inherited processes.

## Validation stance

All current test outcomes, screenshots, and live-provider results must be generated again against the current worktree. Prior round reports are historical context only; they are not current-run passes. Final acceptance remains PARTIAL if real human approval, independent review, PostgreSQL, or other required live gates cannot be completed.
