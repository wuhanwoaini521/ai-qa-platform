# Plan

## Milestones
1. **Kernel safety and traceability**: correlate model invocation, Jev choice, selected candidate, browser dispatch and verification with a per-action correlation ID. Re-observe/revalidate the same-page target immediately before dispatch; stale target must be blocked, evidenced, and replanned without consuming the browser action budget. Add structured Execution Incident classification and bounded recovery.
2. **Long-task state**: keep recent raw action history, compact older actions into bounded searchable chunks, include relevant recalled entries in subsequent AI planning context, and retain replay/evidence references.
3. **Acceptance**: add regression tests for same-URL DOM mutation, event correlation, history compaction/retrieval, and failure outcomes; add an opt-in real-provider/real-Jev local-site E2E test that does not patch providers or decisions. Run it against the effective live config; report blockers honestly.
4. **Regression and review**: run targeted API tests, real Playwright tests, frontend checks and final broad regressions; use agent-browser for real workspace interaction/screenshots; perform a separate structured diff review and fix findings.
5. **Delivery**: write evidence and limitations; stage only this run's owned files and commit by functionality. Do not force push or push over the dirty worktree.

## Expected source scope
- `apps/api/app/services/task_browser_executor.py`
- `apps/api/app/services/task_ai_service.py`
- `packages/qa-core/qa_core/failure/models.py` (only if the shared structured incident model fits the existing taxonomy)
- focused API tests plus an opt-in live AI/Jev test
- focused architecture/acceptance documentation and browser evidence under this run directory

## Acceptance evidence
- Fast pytest test path remains green; Agent uses a real configured model and Jev for a local natural-language browser task, with persisted invocation/decision/action correlation.
- DOM/target changes after planning prevent stale dispatch and cause fresh observation/replanning; failed business criteria remain failures.
- Incident outcome is structured and evidence-linked; patch repair and independent regression are covered by existing end-to-end repair tests (do not weaken assertions).
- Older browser actions remain compactly retrievable after the raw window rolls over; task refresh/replay uses persisted history/events.
- Live browser and workspace UI are interacted with in Chromium; screenshots/traces are saved without secrets.

## Review
No independent sub-agent reviewer is available in this session. Perform a structured second pass over the final diff, challenge correctness/safety/compatibility/error paths and tests, then rerun affected checks.
