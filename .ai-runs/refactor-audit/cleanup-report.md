# Cleanup and Dependency Audit

## Outcome

No package dependency, public API, component, or package was proven unused, so none were removed. Existing REST/SSE/WebSocket clients, repository boundaries, runtime modules, and shared packages have live callers and/or tests; mechanical consolidation would add compatibility risk without demonstrated redundancy.

The confirmed cleanup was limited to the unsafe automatic repair path in `FailureWorkflowService`:

- Removed automatic patch application and automatic verification-run creation from analysis.
- Removed the unattended follow-up AI/Jev retry loop and its retry-only context, candidate exclusion, and terminal failure helper.
- Kept explicit human Apply, explicit exact-node verification, and configured rollback safeguards.
- Kept `repair.max_attempts` in config/model for compatibility, documented that it has no runtime effect.

No dependency manifest or lockfile changed. Playwright in the active environment was aligned to the repository-required `1.62.0`; this did not change project dependency files.

## Data and artifact safety

- Preserved the pre-existing `mise.toml` edit (`rtk = "latest"`); it is excluded from task staging.
- Did not alter `.env`, repository `runtime/`, or pre-existing `.ai-runs` data.
- Browser/API acceptance used `/tmp/aiqa-refactor-audit-run`; its isolated servers, browser profile, database, artifacts, and workspace were stopped/removed after testing.

## Validation

`ruff check`, `ruff format --check`, i18n parity, ESLint, full test suite, and `git diff --check` passed. See `test-results.md` for the opt-in live acceptance failure and environment limitations.
