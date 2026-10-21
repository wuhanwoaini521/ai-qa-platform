# Round 20 — CI parity and the PostgreSQL channel

## Why this exists

`.github/workflows/ci.yml` runs only on `push`/`pull_request` to `main`, and this overnight run is
forbidden to push. There is therefore **no CI run evidence**, and CI stays BLOCKED. What can be
verified locally is whether the exact CI commands pass on this commit — that is what the table below
records, run 2026-10-21 on HEAD of the overnight branch.

## The CI commands, run locally

| CI job | Command as written in ci.yml | Local result |
|---|---|---|
| backend | `uv run ruff check .` | pass (488 files) |
| backend | `uv run ruff format --check .` | pass (488 files already formatted) |
| backend | `uv run python scripts/export_openapi.py --check` | `OpenAPI contract is current` |
| backend | `uv run pytest -v` | see `regression/backend-sqlite.txt` |
| backend-postgres | `AI_QA_TEST_DATABASE_URL=postgresql+asyncpg://… uv run pytest apps/api -v` | see `rounds/r20-postgres.txt` |
| frontend | `pnpm --filter @ai-qa/web test` | 223 pass / 0 fail |
| frontend | `pnpm --filter @ai-qa/web api:types && git diff --exit-code -- apps/web/src/api/generated-schema.d.ts` | regenerated in this round; diff is part of the commit |
| frontend | `pnpm --filter @ai-qa/web typecheck` | clean |
| frontend | `pnpm --filter @ai-qa/web lint` | clean |
| frontend | `pnpm --filter @ai-qa/web build` | built in 52 s |
| windows | `python scripts/task.py setup| lint | test` | not run (no Windows host in this environment) → BLOCKED |

## Defects the PostgreSQL channel found (all three were invisible on SQLite)

1. **`stored_artifacts.created_by` was `VARCHAR(36)` but the product stores a label.** A recorder run
   sets `requested_by: "Recorder · <case name>"`, and artifact stamping copies that same string into
   `created_by`. PostgreSQL raised `StringDataRightTruncationError: value too long for type character
   varying(36)` and the discovery→coverage E2E run ended `ERROR` with zero executions. Fixed by widening
   the column to 100 (migration `0021_artifact_actor_width`) to match `test_runs.requested_by`, which the
   value comes from.
2. **Index name drift on `ai_invocations.step_id`.** Migration `0018_ai_invocation_step` created
   `ix_ai_invocations_step`, while the model declared `index=True` (SQLAlchemy names that
   `ix_ai_invocations_step_id`). `compare_metadata` reported `remove_index`/`add_index` pairs on every
   fresh database. Fixed by declaring the index explicitly in `__table_args__` with the migration's name —
   no data migration needed.
3. **`pytest apps/api` collected a router as a test module.** `apps/api/app/api/test_designs.py` is a
   FastAPI router whose name starts with `test_`; pytest imported it and collected the *imported*
   dependency `test_design_access`, failing with `AttributeError: 'TopRequest' object has no attribute
   'path_params'`. A root-run `uv run pytest` never saw it because `testpaths` excludes `app/api`, so the
   CI command was red while local runs were green. Fixed with `apps/api/conftest.py`
   (`collect_ignore_glob = ["app/api/*.py"]`).

Two further failures were *stale tests*, not product defects: recovery of interrupted AI invocations and
of interrupted requirement analyses became deadline-based in Round 18 (a second replica may be waiting on
the model right now), and the two tests still inserted a *fresh* row and expected it to be closed. They now
assert both halves: a stale row is closed, a fresh row is left alone.

## Verdict

- CI as a service: **BLOCKED** (no remote runs; pushing is forbidden in this mission).
- CI command parity on this commit: **PASS**, with the three defects above fixed first.
- PostgreSQL test channel: **PASS** on PostgreSQL 16 (`postgres:16-alpine` in Docker, port 55432).
