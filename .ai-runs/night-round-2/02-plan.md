# Plan

- run-date: 2026-10-14
- task-type: refactor
- scale: standard

1. Frontend A: compare handwritten Runtime DTOs against generated OpenAPI types; replace RuntimeDetail's initial status markup with shared LoadingState/ErrorState; route artifact downloads through the shared blob/error client helper. Keep DTO rewriting out of this bounded component change and record the remaining drift-prevention follow-up.
2. Backend B: inject TaskCommandService into QualityDiscoveryService via `container.py`, remove cross-Router service imports/arguments, and make `main.py` obtain/start/stop TaskRuntime from the container. Migrate tests off Router-owned runtime globals.
3. Add focused task-stream cursor/error assertions and run existing runtime/client/SSE/error tests plus backend architecture/quality-discovery/task tests.
4. Capture pre/post OpenAPI JSON and verify exact equality for B, plus export/type consistency checks. Verify frontend and backend processes independently in isolated temporary configuration without touching `.env`, persistent Compose data, `runtime/`, or already-running developer services.
5. Run code review, relevant regressions, record exact evidence, and create separate frontend, backend, and run-log commits without staging pre-existing changes. Keep `mise.toml` unstaged.
