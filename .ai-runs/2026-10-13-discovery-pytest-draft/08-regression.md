# Regression

## Commands and outcomes

- `python scripts/task.py test` — final implementation run: backend **738 passed, 8 skipped**; frontend **138 passed**; TypeScript typecheck, ESLint, and Vite production build passed.
- `python scripts/task.py lint` — Ruff check/format, translation parity, and frontend ESLint passed (**25 namespaces, 2 languages, 2,909 keys**).
- `uv lock --check` — passed.
- `git diff --check` — passed.
- After the final formatting-only adjustment, `mise exec -- uv run pytest apps/api/tests/test_quality_discovery.py::test_discovery_draft_api_waits_for_approval_before_workspace_write -q` — **1 passed**.
- Real browser review used the local dev stack and checked the completed-journey UI at 1440×1000, 768×1024, and 390×844. Evidence is in `evidence/` and observations are in `05-ui-review.md`.

## Coverage

- Discovery service compatibility and graph evidence reconstruction.
- Recorder select-by-value generation with legacy label selection retained.
- Task generation, source assertion policy, skipped browser stages, approval diff/wait state, rejection/no-write, and explicit-approval/write/run positive path.
- UI rendering, control visibility/focus, and responsive page width at desktop/tablet/phone.

## Not run / limitations

- PostgreSQL integration lane was skipped because `AI_QA_TEST_DATABASE_URL` is not configured.
- Opt-in live provider/browser acceptance tests remain skipped by repository configuration.
- Browser review did not activate the CTA against the persistent development database; the API/runtime integration test exercised both rejected and approved paths with an isolated local fixture page.
- Vite emitted its existing advisory about large chunks; build succeeded.

No regression found. Existing UI shell navigation clipping at narrow widths is recorded as a non-blocking adjacent P2 in the UI review; document width did not exceed the viewport.
