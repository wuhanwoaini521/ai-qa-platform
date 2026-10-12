# Dogfood Report: AI QA Platform

| Field | Value |
|-------|-------|
| **Date** | 2026-10-12 |
| **App URL** | `http://127.0.0.1:5173` |
| **Browser session** | `platform-stability-41b3d38a2cfa` (isolated Chrome/CDP) |
| **Scope** | Dashboard, Projects, Workspace requirements/cases/automation/results, Runs, Library, Quality, Settings, Workers, Security, Tasks/Workflow; focused end-to-end repair journey. |

## Outcome

The first-pass review reproduced three user-visible state/integration failures. Fixes resolved those repros. Extending the journey through a real locator failure and repair exposed additional source-mapping, persistence, and status-copy defects; those were fixed and regression-tested. **No reproduced issue remains open in the exercised flows.**

| Severity | Open | Fixed in this round |
|----------|------|---------------------|
| Critical / High | 0 | 0 |
| Medium | 0 | 7 |
| Low | 0 | 0 |

One residual risk remains: a scaffold operation that fails after writing files/bindings can still leave partial side effects. The reproduced JSON-corruption cause is fixed, but general failure compensation/atomicity was not added. Existing acceptance records were not retroactively migrated.

## Findings and fixes

### ISSUE-001 — Workspace requirement count stayed stale after creation — **Fixed**

Creating a requirement opened its detail but left the workspace stage at “no requirements” until reload. `RequirementsPage` now reports the change to its parent and selects the saved requirement. The count updated immediately in the browser; the saved requirement remained intact.

Evidence: `screenshots/after/requirement-created-1440.png` and `screenshots/after/requirement-created-after-reload-1440.png`.

### ISSUE-002 — Real-model scaffold result JSON was corrupted — **Fixed for reproduced failure**

Real `openai-compatible · deepseek-flash` scaffold requests failed while parsing a serialized result: free-text sensitive-value redaction removed escaped JSON quotes. `AITraceEvent.redact_content` now leaves structured `operation.result` events intact, with a regression test.

After the fix, the real-model scaffold generated a draft, the case was activated, and run `run_63cec6f0e680` **passed 1/1** (`test_submitting_valid_credentials_opens_account_state`). The original failed attempts had already written draft files and a draft binding before the UI error; those side effects were not rolled back. This remains a residual risk for other post-write failures.

Evidence: `screenshots/after/studio-generated-draft-1440.png`; trace and run artifacts in this directory.

### ISSUE-003 — Workspace automation coverage stayed stale after binding changes — **Fixed**

Changing an automation binding did not refresh the parent workspace summary. Binding updates now propagate to the workspace. Browser toggles showed immediate `1/1 → 0/1 → 1/1` updates without reload.

Evidence: `screenshots/after/binding-activated-count-stale-1440.png` and `screenshots/after/binding-count-after-reload-1440.png`.

### ISSUE-004 — Runtime locator failures could not produce a source-mapped patch — **Fixed**

Playwright’s captured `internal:role=...` failure selector did not identify the Python source expression, leaving a repair proposal without a usable diff. Repair proposals now map a runtime selector to one unique AST source call; ambiguous, stale, or unmappable targets are rejected, and review/apply use the mapped source expression.

The live repair journey mapped the failing call to `page.get_by_role("button", name="continue", exact=True)`, presented a source diff, and applied the reviewed change.

### ISSUE-005 — Generated role locator weakened `exact=True` — **Fixed**

A replacement could drop the observed exact-match constraint. Locator generation now preserves `exact=True`, with regression coverage. The accepted Jev candidate was `get_by_role("button", name="Continue", exact=True)`. Earlier semantically unrelated candidates were rejected by review and were not applied.

### ISSUE-006 — Apply/rollback state was not consistently persisted or presented — **Fixed for new transitions**

Manual patch application and rollback now persist the updated proposal plus `changes_applied=True/False`; the workflow UI reflects the workspace change and actual rerun result. Regression coverage verifies both transitions.

The live browser acceptance repair was applied and rerun successfully before this persistence fix landed. That historical analysis row was not backfilled; it may still contain the earlier `changes_applied` value. New transitions are covered by tests.

### ISSUE-007 — A passed repair still showed “not verified” and stale rerun advice — **Fixed**

The result panel used “Analysis complete · Repair not verified” as generic analysis-completion copy and continued to show locator-repair/rerun recommendations after a successful retest. The completion label now reports analysis completion only, and recommendations are hidden once verification passes.

After the fix, the browser showed “Actual verification passed” and “Retest status: Actual verification passed,” with no stale “not verified” label or rerun advice. Responsive checks at 1440×1000, 768×1024, and 390×844 found no document-level horizontal overflow (`scrollWidth` matched viewport width); contained workflow/stage rails remain scrollable.

Evidence: `screenshots/after/failure-workflow-desktop-1440.png`, `failure-workflow-tablet-768.png`, and `failure-workflow-mobile-390.png`.

## End-to-end acceptance evidence

- Real model diagnosis used `openai-compatible`; Jev selected `candidate_1` (`jev-1.13.0`) after page evidence and semantic review.
- The reviewed source change corrected the button accessible-name case while preserving exact matching.
- Original failure run `run_a598aa97f191` was rerun as `run_36e1e253ade68196759635bcde22f7f1`: **PASSED, 1/1**, for `tests/test_sign_in_locator_repair.py::test_sign_in_submit_is_activatable`.
- A diagnosis/proposal alone was not treated as a repair; only applying the reviewed patch and passing the original failing test counted as success.

## Automated validation

- Backend suite: **675 passed, 7 skipped** on the SQLite lane. PostgreSQL was skipped because `AI_QA_TEST_DATABASE_URL` was not set.
- Focused repair/trace suites: **95 passed, 1 skipped**; trace/redaction suites: **29 passed**.
- Web tests: **137 passed**.
- Python Ruff check/format, frontend ESLint, i18n parity (25 namespaces, 2 languages, 2,906 keys), TypeScript typecheck, and production build passed.
- Build retains the existing large Monaco editor chunk warning (>500 kB). The full Python suite emitted collection/fixture warnings and an `aiosqlite` connection-cleanup `SAWarning`; tests still passed.

## Remaining unverified / follow-up

- PostgreSQL-specific lane, Linux/Windows CI, Firefox/WebKit, and full screen-reader validation were not run.
- Video recording was unavailable (`ffmpeg` is not installed).
- The previously observed Dashboard load delay remains incompletely attributed.
- The earlier Golden Demo TC-002 button-name mismatch is from a separate prior run and was not addressed in this round.
- General rollback/compensation for scaffold failures after file/binding writes remains outside this fix; do not infer that sandbox data or processes were cleaned up.
