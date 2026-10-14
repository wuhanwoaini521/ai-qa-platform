# Round 4 codebase cleanup — final acceptance

## Verdict: PARTIAL

The scoped fixes are implemented and passed local regression, lint, typecheck, build, and browser checks. No known correctness blocker remains in the executed lanes. Acceptance stays **PARTIAL** because the required independent review was unavailable; Docker, PostgreSQL concurrency, cross-platform CI, and other listed gates were not run.

## Delivered

- Runtime-owned idle BrowserRuntime cleanup, explicit shutdown cleanup through the existing port/adapter, and setup-failure cleanup that preserves the original exception.
- Recurrence error/retry UI with stale-response protection; browser-verified failure → retry recovery and delayed stale response handling.
- Removal of only the unreachable standalone failure queue branch and dead supporting strings/styles; `/failures` and embedded failure workflow remain.
- Removed the worker image's redundant unpinned Playwright install; resolved version remains **1.62.0**.
- No AI/Jev call, repair Apply, external write, source write, REST/schema change, or unrelated page/provider/runtime removal.
- Audit and before/after cleanup metrics: `ponytail-audit.md`.

## Verification

- `uv run pytest -q`: **755 passed, 8 skipped, 0 failed**.
- Web tests: **147 passed**; TypeScript typecheck, ESLint, and production build passed. Build retains the existing Monaco chunk-size warning.
- Ruff check and format, i18n parity, and scoped staged-diff whitespace checks passed.
- Chrome recurrence error/retry and stale-response race checks passed; evidence is in this directory.
- Basedpyright did not run because uv's attempt to build `nodejs-wheel-binaries==24.19.0` failed before checker startup. Docker is not installed, so no worker image build is claimed.

## Review and remaining gates

- Implementer serial second-pass review found no unresolved P0/P1 blocker. It is not independent review.
- Orca review is blocked by `Unable to determine Orca.app path from symlink: /usr/local/bin/orca`.
- PostgreSQL concurrency, Windows/Linux CI, axe, a second browser engine, and live AI/Jev acceptance remain unrun. The human-approval/source-write boundary was preserved; no live AI/Jev action was needed or invoked for these fixes.

## Commits

- Source: `42c9ee2` — `fix: close idle browsers and clarify failure history`.
- This evidence/report directory is committed separately as a scoped companion commit.

## Worktree preservation

After the companion report commit, `git status --short` is expected to retain the following inherited unrelated changes; these were not staged or committed. In particular, `mise.toml` was preserved.

```text
 M .github/workflows/ci.yml
 M apps/api/app/api/failures.py
 M apps/api/app/repositories/failure_analysis_repo.py
 M apps/api/app/services/failure_service.py
 M apps/api/app/services/failure_workflow_service.py
 M apps/api/app/services/locator_decision_service.py
 M apps/api/tests/test_architecture_boundaries.py
 M apps/api/tests/test_failure_snapshot.py
 M apps/api/tests/test_failure_workflow.py
 M apps/api/tests/test_live_locator_repair_acceptance.py
 M apps/api/tests/test_locator_decision_service.py
 M apps/web/package.json
 M apps/web/src/api/client.ts
 M apps/web/src/components/FailureWorkflowPanel.tsx
 M apps/web/src/i18n/locales/en/failures.json
 M apps/web/src/i18n/locales/zh-CN/failures.json
 M apps/web/src/pages/FailuresPage.tsx
 M apps/web/src/types/index.ts
 M config/config.example.yaml
 M docs/CONFIGURATION.md
 M docs/FAILURE_INTELLIGENCE.md
 M mise.toml
 M package.json
 M packages/platform-config/platform_config/models.py
 M pnpm-lock.yaml
?? .ai-runs/2026-10-13-second-round-core-objectives/
?? .ai-runs/night-round-1/
?? apps/api/tests/test_openapi_contract.py
?? apps/web/src/api/generated-schema.d.ts
?? apps/web/src/api/openapi.json
?? scripts/export_openapi.py
```

The residual edits in `FailuresPage.tsx` and the failure locale files are the inherited, unstaged hunks; only the codebase-cleanup hunks were included in the source commit. No push was performed.
