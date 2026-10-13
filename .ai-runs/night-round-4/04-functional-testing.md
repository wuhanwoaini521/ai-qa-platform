# Functional testing — night round 4

## Regression coverage

- TDD red check: the new state-machine test initially failed because `PATCH_READY` did not offer `REJECT`; the API test returned 404 because no reject route existed. Both failures matched the diagnosed gap.
- Final command: `UV_NO_SYNC=1 uv run --no-sync pytest apps/api/tests/test_failure_workflow.py apps/api/tests/test_locator_repair_state_machine.py apps/api/tests/test_locator_repair_eligibility.py apps/api/tests/test_openapi_contract.py apps/api/tests/test_architecture_boundaries.py -q`
  - **99 passed**, 2 existing `PytestCollectionWarning`s for the Pydantic `TestRunCreate` model.
  - Includes API rejection/persistence, apply-denied/no-source-change, state-machine action/transition, eligibility, explicit human Apply/verification, architecture boundaries, and FastAPI/OpenAPI parity.
- `UV_NO_SYNC=1 uv run --no-sync pytest apps/api/tests/test_live_locator_repair_acceptance.py -q`: **2 skipped**; external real-provider acceptance was not enabled. Prior rounds' real AI + Jev acceptance is carried forward; no provider was called in this round.
- `pnpm --filter @ai-qa/web typecheck`: passed.
- `pnpm --filter @ai-qa/web test`: **146 passed**.
- `pnpm --filter @ai-qa/web lint`: passed.
- `pnpm --filter @ai-qa/web build`: passed. Existing Vite warning remains that several generated chunks exceed 500 kB; no build errors.
- `uv run --no-sync ruff check ...` on changed Python source/tests: passed.
- `uv run --no-sync ruff format --check ...`: passed (7 files already formatted).
- `UV_NO_SYNC=1 uv run --no-sync python scripts/export_openapi.py --check`: current.
- `git diff --check`: passed.

## Actual API/browser journey

Used system Chrome through agent-browser against the actual Vite + FastAPI application, configured with a disposable SQLite database at `/tmp/night-round-4/qa.db`; the regular application database and workspaces were not touched. The fixture contained one synthetic failed run, a trusted `PATCH_READY` proposal, and an unchanged source file.

1. Logged in to the isolated instance and opened the fixture's failure workspace.
2. The proposal displayed the new **Reject proposal** action alongside the explicit Apply action.
3. Clicked Reject; browser network evidence records `POST /api/failures/{id}/analyses/{id}/reject` → **200**.
4. Reloaded the page. The proposal and analysis history still show the rejection, with the human-readable “no source changes” message. Apply and Reject are no longer offered; reanalysis remains available.
5. A follow-up API check read `BLOCKED / HUMAN_REJECTED`, only `START_ANALYSIS`, and a persisted `repair.rejected` event. A follow-up Apply request returned **422**, and the original source content matched byte-for-byte.
6. axe audit scoped to `.failure-repair-proposal` at 360 px: **0 violations**, **0 incomplete**. `document.documentElement.scrollWidth` equalled the viewport at 1440, 768, and 360 px.

Evidence: `evidence/api-rejection.json`, `evidence/a11y-rejected-proposal-mobile.json`, `evidence/proposal-before.png`, `evidence/proposal-rejected-before-reload.png`, and the post-reload desktop/tablet/mobile screenshots.

No AI/Jev call, TestRun execution, or source Apply occurred in this browser journey. Browser console showed no page errors; the only Vite reconnect notice was caused by restarting the local dev server to point at the disposable API. The bundled Chrome 155 initially failed to launch due to a macOS VideoToolbox symbol mismatch; the installed system Chrome was used successfully.

## Not run / carried forward

- Full repository regression and independent review are deferred to round 5.
- PostgreSQL and Windows/Linux validation were not available in this round; the new behavior ran against the project's SQLite test backend and an isolated SQLite browser instance.
- Real AI + Jev credentials were deliberately not invoked; the gated acceptance remains skipped here.
- Initial unscoped `python`/`rtk pytest` wrappers selected a mise Python without FastAPI/pytest; all final checks used the project's `uv run --no-sync` environment. This was a runner-selection issue, not a product failure.
