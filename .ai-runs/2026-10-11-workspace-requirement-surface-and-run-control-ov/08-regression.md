# Regression

## Checks

- Frontend lint: PASS.
- Frontend tests: PASS (113/113).
- Frontend production build: PASS; only the existing large Monaco chunk advisory.
- Browser error/console checks: no page errors observed.
- Desktop/tablet/phone/narrow-phone geometry and keyboard dialog regression: PASS.
- Shared Cases stage header: PASS. Follow-up Cases analysis viewport check at 1484×880 and 390×844: PASS; conditional progress action layout at 1484/768/390: PASS with no document overflow.
- Dark-theme variable/render check: PASS.
- `git diff --check`: PASS.

## Scope Control

No API, business data, AI, run, queue, dependency, lockfile, stage, or commit operation. Existing worktree edits were preserved. `.ai-runs/` is not ignored by the current `.gitignore`; this run record remains untracked and no files were staged.
