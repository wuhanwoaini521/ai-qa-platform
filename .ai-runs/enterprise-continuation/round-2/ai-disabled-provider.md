# Round 2 · AI/Jev disabled-mode reliability verification

Date: 2026-10-16 · branch `agent/wsl-continuation` · isolated API on `127.0.0.1:8010`

## Reproduction before fix

Started a separate API instance with `QA_AI_ENABLED=false JEV_ENABLED=false` against the local dev database.
The API health endpoint was healthy, but dependency construction made unrelated read routes fail:

| Request | Before | After |
| --- | ---: | ---: |
| `GET /api/ai/status` | 500 | 200 (`operational_state=DISABLED`, `failure_reason=ai_disabled`) |
| `GET /api/runs` | 500 | 200 (`[]`) |
| `GET /api/failures` | 500 | 200 (`[]`) |
| `GET /api/ai/system-health` | 200 | 200 (`degraded`, correctly reports disabled AI) |
| `POST /api/decision/runtime-check` | — | 200 (`runtime=DISABLED`, `connectivity=NOT_CHECKED`) |

The prior 500 traceback ended with the exact error:
`RuntimeError: AI provider is disabled by the effective AppConfig`

Root cause: FastAPI eagerly constructed `TestRunService`, `FailureService`, and `AIService` as route dependencies. Each created `ProductionQAOrchestrator`, whose constructor immediately called `AIProviderRegistry.get_provider()`. With AI disabled, provider construction raised before otherwise provider-independent GET handlers could execute.

## Fix

`packages/qa-core/qa_core/orchestrator/orchestrator.py` now resolves and caches the provider on first access via the existing `ai_provider` attribute. Orchestrator composition and deterministic non-AI diagnosis remain available with AI disabled; an actual provider-backed operation still attempts provider resolution and raises the existing disabled-provider error. This avoids fallback or false success and does not add a second provider/runtime abstraction.

## Verification

- Real API, `QA_AI_ENABLED=false JEV_ENABLED=false`: enumerated 43 parameterless GET paths from OpenAPI. No request returned 5xx; parameter-required paths returned expected 422. This included `/api/ai/status`, `/api/runs`, and `/api/failures`.
- Real API: `POST /api/decision/runtime-check` returned `200`, `runtime=DISABLED`, and `connectivity=NOT_CHECKED`; no Jev request was made.
- Isolated integration test: `apps/api/tests/test_ai_provider_settings.py::test_ai_disabled_keeps_status_and_read_endpoints_available` verifies disabled status, `/api/runs` and `/api/failures` reads, and that a real AI analysis request fails honestly with HTTP 502 rather than falling back or claiming success.
- Core regression: `packages/qa-core/tests/test_migrated_core.py::test_production_orchestrator_defers_provider_creation_until_use` verifies constructing the orchestrator is safe while disabled and provider access still raises the explicit disabled error.
- `uv run --no-sync pytest packages/qa-core/tests/test_migrated_core.py apps/api/tests/test_ai_provider_settings.py -q --no-header -p no:cacheprovider` → **20 passed**.
- Ruff check and format check for the three changed Python files → PASS.
- Independent reviewer of the focused diff → no findings.

## Safety / limits

No provider call or external write was made during disabled-mode verification. The test database is per-test and isolated; the live route sweep used only reads and the explicit disabled Jev runtime check. This does not substitute for the remaining real-AI/Jev repair safety matrix (approval, application, exact verification, rollback, interruption), which remains open.
