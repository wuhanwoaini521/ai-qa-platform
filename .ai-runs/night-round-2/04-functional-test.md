# Functional / Contract Tests

- run-date: 2026-10-14
- task-type: refactor
- scale: standard

## Frontend
- `pnpm --filter @ai-qa/web test`: **146 passed**.
- `pnpm --filter @ai-qa/web typecheck`: passed.
- `pnpm --filter @ai-qa/web lint`: passed.
- `pnpm --filter @ai-qa/web build`: passed; Vite emitted its existing large-chunk advisory (>500 kB), no build error.
- Runtime TypeScript field-name self-check against `apps/web/src/api/openapi.json`: `RuntimeSpan`, `RuntimeStep`, `RuntimeEvent`/`NormalizedRuntimeEvent`, `RuntimeArtifact`, and `RuntimeSnapshot` each had **zero API-only or TS-only fields**. Defaulted Pydantic values are required by the current UI DTO but optional in generated OpenAPI declarations; nullability/deep nested typing remains handwritten and is a follow-up.
- Generated contract verification: `openapi-typescript 7.13.0` wrote to `/tmp`; output was byte-identical to the existing generated declaration. No tracked/untracked contract artifact was overwritten.

## Backend / Public API
- `apps/api/tests/test_openapi_contract.py`, `test_error_envelope.py`, `test_failure_diagnosis_stream.py`, `test_runtime_event_cursor.py`, `test_runtime_events.py`: **27 passed, 3 collection warnings**.
- Canonical `app.openapi()` JSON captured before and after backend implementation: `cmp` returned equal; `python scripts/export_openapi.py --check` (through `uv run --package api`) reported **OpenAPI contract is current**.
- `test_quality_discovery.py` draft success and non-replayable evidence tests: **2 passed**.
- `test_discovery_draft_api_waits_for_approval_before_workspace_write`: **1 passed**; no workspace write before approval or after rejection; explicit approval produces the file and completed test run.
- `test_agent_tasks.py`: **68 passed**; after adding the `Last-Event-ID` replay/malformed-cursor assertions, the focused SSE test rerun also passed (**1 passed**).
- `test_requirement_lifecycle_workflow.py`: **9 passed**.
- Browser/task behavior tests for changed container access: **3 passed** in `test_browser_agent.py`; API end-to-end task runtime test **1 passed** in `test_browser_agent_e2e.py`.
- `test_architecture_boundaries.py`: **17 passed**.
- Targeted backend `ruff check` and `ruff format --check`: passed. `python scripts/task.py lint`: passed (Ruff, formatting, 25 i18n namespaces / 2 languages / 2912 keys, ESLint).
- `git diff --check`: passed.

## Independent Process Startup / UI Evidence
- Started an isolated API process on `127.0.0.1:8012` with a temporary config, SQLite DB, runtime/workspace/artifact dirs, and temp secret. `/api/health/ready` returned `{"status":"ready","database":"ok","storage":"ok"}`.
- Started Vite separately on `127.0.0.1:5191`, proxying to that isolated API. Vite document and `/api/health/ready` proxy both returned HTTP 200.
- Browser functional check loaded RuntimeDetail from a mocked API RuntimeSnapshot and verified the tabs/actions render. A separate aborted Runtime request rendered the shared error state with an accessible Retry button; clicking Retry exercised the callback and retained the recoverable state. Screenshots: `evidence/runtime-detail-success.png`, `evidence/runtime-detail-error.png`.
- Agent Browser's bundled Chrome 155 failed on this host (macOS 12.7.6 / VideoToolbox symbol mismatch); Playwright 1.62.0 had no installed browser and its installer does not support macOS 12. The existing Google Chrome 150 was launched with a fresh temporary profile and agent-browser attached over local CDP. No user browser profile was opened. Temporary API/Vite/Chrome processes and the isolated data directory were stopped/removed; existing API `:8001` and Vite `:5174` remained listening.

## Not Run
- Full workspace regression and Worker-specific suite were not rerun; validation was limited to affected Web/API boundaries and related tests.
- PostgreSQL tests were not run because no isolated disposable PostgreSQL instance was configured. SQLite test fixtures were temporary and do not substitute for PostgreSQL coverage.
- `basedpyright` was not run: `UV_NO_SYNC=1 uv run --package api basedpyright ...` could not find the executable. Python lint/format and runtime tests passed.
