# Plan and milestones

## Milestones

1. **Baseline and live exploration** — preserve initial Git state; inventory actual routes/services/configuration without exposing secrets; use a named browser session; capture Before screenshots and exercise each requested module. Build a page/feature coverage matrix and document concrete reproducible findings.
2. **Targeted repair loops** — for each verified high-impact issue, record evidence/root cause, add or update a public-seam regression test, implement the smallest coherent fix, rerun its tests, and verify the interaction in the live browser. Keep modules/API contracts intact.
3. **Real acceptance journeys** — use uniquely named, non-destructive project data for normal run, failure→manual repair→rerun, AI+Jev locator repair when genuinely configured, Studio/browser/debug/failure handoff, and reload/history. Mark any blocked scenario NOT AVAILABLE or FAIL with evidence.
4. **Review and final regression** — inspect After screenshots at desktop/tablet/phone, check keyboard/a11y and browser console/network, perform a challenge-first independent code review, fix blocking findings, and rerun affected plus broad final suites.
5. **Delivery** — compare staged paths against the initial snapshots, categorize commits, ensure no secrets/runtime/user changes enter, push only the task branch normally, and verify remote SHA/status.

## Verification strategy

- Discovery: README, repository instructions, actual route/nav manifests, task runner, CI and service health.
- Static/backend/frontend: `python scripts/task.py lint`, `pnpm --filter @ai-qa/web typecheck`, frontend unit tests, production build, and `uv run --no-sync pytest -q` (or repository-approved equivalent); inspect PostgreSQL availability and run its lane only with a safe test database URL.
- Runtime/API: health/readiness, representative authenticated API success/error and persistence checks through the existing service; do not mutate production data or restart services unnecessarily.
- Browser: existing system Chrome/CDP-compatible agent-browser with a task-scoped session; visit the requested modules, test key interactions and saved state, capture Before/After at 1440/768/360–390 widths; separate axe findings from incomplete/manual checks.
- Business seams: user-facing browser flow plus API/database persistence as exposed by the platform; real AI + Jev provider operation kept separate from mock/provider unit tests.
- Regression: rerun changed-area tests, frontend and backend suites, relevant API/browser journeys, and platform lint/typecheck/build on final code. Report exact counts, blockers, and any pre-existing failures.

## Guardrails / acceptance

- Do not stage or overwrite pre-existing work; do not perform force push, reset/clean, schema/data reset, secret output, or confidence/assertion reductions.
- Each fix requires reproduced evidence, a regression test where applicable, live behavior verification, and a second-pass code review.
- Pass only if core requested journeys and required checks have direct positive evidence. If external lanes or real AI/Jev are unavailable, state why and use PARTIAL; any unresolved blocking core defect is FAIL.
- Stage only reviewed task-specific hunks/files, making separate commits by functional category; push `agent/ai-qa-platform-stability` only after final verification.
