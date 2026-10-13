# Regression / Acceptance

- run-date: 2026-10-14
- task-type: refactor
- scale: standard

| Requirement | Evidence | Result |
|---|---|---|
| A: frontend-only core component update | RuntimeDetail shared loading/error UI; front typecheck, lint, build, 146 tests; browser success/error/retry screenshots | PASS |
| B: backend-only internal refactor | Quality Discovery service composition and TaskRuntime container ownership; API tests and approval workflow | PASS |
| API contract unchanged in B | Canonical OpenAPI before/after comparison; OpenAPI export check; contract tests | PASS |
| Public DTO/OpenAPI alignment check | Generated contract output matches; checked RuntimeSpan/Step/Event/Artifact/Snapshot field-name parity | PASS with handwritten nested type follow-up |
| SSE/task state/error/reconnect | Task event terminal/replay test; Last-Event-ID replay; malformed cursor 400; error envelope/failure stream/runtime cursor tests; web transport/run-store tests | PASS |
| Independent process startup | Isolated API health readiness and separate Vite/API proxy both HTTP 200 | PASS |
| Human approval boundary | Discovery proposal remains draft; no file pre-approval/rejection; write only after explicit approval | PASS |
| PostgreSQL coverage | No isolated disposable PostgreSQL instance configured | NOT RUN |
| Full monorepo/API+Worker regression | Scoped impacted suites and global lint run; full test matrix not repeated | NOT RUN |
| Independent code review | Not available/performed; this is not represented as independent | NOT RUN |

No API contract or source-write safety regression was observed in the tested scope. Multi-API-replica background task ownership remains process-local; do not scale API replicas until a shared ownership/coordinated recovery mechanism is provided.
