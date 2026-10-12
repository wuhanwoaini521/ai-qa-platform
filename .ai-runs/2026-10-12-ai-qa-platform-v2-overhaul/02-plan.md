# AI QA Platform V2 overhaul

- run-date: 2026-10-12
- task-type: ui-redesign
- scale: standard (operational scope: large)

## Milestones

### M1 — Live product discovery (in progress)
- Explore primary user journey via `agent-browser` before source changes.
- Capture reproducible findings, screenshots, route coverage, settings status, and environmental blockers.
- Create only an additive isolated local sandbox.

### M2 — Repository understanding and root-cause validation
- Inspect repository/worktree baseline, recent commits, relevant pages, project selectors, workspace task/run state, language-service launch path, tests, CI, and runtime config.
- Validate each selected issue against callers and public contracts; reject findings that are only stale data or expected loading.
- Produce architecture candidates/report under the OS temp directory; choose changes aligned with this authorized overhaul.

### M3 — TDD vertical slices and implementation
- Add regression tests before each fix.
- Candidate slices: (1) distinguish workflow-task completion from persisted test-run status; (2) disambiguate duplicate project records in project lists/selectors without mutating data; (3) restore an available Python language-service launch path and useful error feedback; (4) improve dashboard progressive loading only if profiling proves an avoidable serial dependency.
- Retain route, API, persistence and visual-system contracts; preserve all pre-existing diffs.

### M4 — Real functional and AI + Jev journey
- Complete sandbox requirement → scenario → case → automation/script binding → real local run → per-case results/failure path.
- Verify AI and Jev provider/model records from the live workflow; never substitute a mock or accept fallback.
- Do not apply an AI repair without an explicit preview and approval flow; keep any generated script confined to the sandbox.

### M5 — Independent review, UI review, regression and delivery
- Re-read the task diff with a challenge-first code-review lens; use an independent reviewer only if a reviewer tool is available.
- Verify desktop/tablet/mobile, theme/language, keyboard/focus and axe findings for affected routes.
- Run targeted frontend/backend suites, lint/typecheck/build and the risk-appropriate full regression; record unavailable PostgreSQL/cross-platform/browser checks explicitly.
- Prepare categorized commits from only current-task hunks, verify staged diffs against the saved baseline, then push normally if the commit boundary is safe.

## Acceptance criteria

- Dashboard, Projects, Workspace, Automation, Runs and Failure status remain internally consistent; AI task success cannot be presented as a test pass when no test run exists.
- Same-name projects can be distinguished in project listings and selectors without changing stored project names or records.
- Python editor service is available when the supported runtime is installed, or the actual spawn failure is surfaced with a recoverable/diagnostic path.
- Critical user path works end-to-end in the V2 sandbox with persisted test-run results and exact AI/JeV provider evidence, without external production targets or fallback.
- Modified UI behaves at 1440px desktop, 768px tablet and ~390px mobile, including empty/loading/error states and existing bilingual/theme behavior.
- Relevant tests, independent review and regression have recorded real results; no API contract, secret, runtime file, or pre-existing user change enters commits.
- Final report states `PASS`, `PARTIAL` or `FAIL` based on evidence and lists all blockers.

## Final milestone status

- **M1 — complete:** real browser exploration and findings recorded in `reports/v2/product-audit/REPORT.md`; isolated sandbox created.
- **M2 — complete:** confirmed duplicate identity, task/TestRun conflation, mobile table overflow, and language-service environment dependency state. Dashboard remains a measured but not fully isolated performance candidate.
- **M3 — complete for verified frontend defects:** added project disambiguation, task/TestRun status separation, case-ID fallback, and accessible responsive project-table scrolling. Did not change the API/data contract, Dashboard, or language-service installation.
- **M4 — complete:** configured AI + Jev requirement analysis succeeded without fallback; one sandbox case was bound and run through the real TestRun executor, persisting 1/1 PASS.
- **M5 — automated and browser review complete; delivery still requires selective commit/push:** 137 web tests, 669 backend tests, lint/typecheck/build/ruff, desktop/tablet/mobile screenshots, and axe checks are recorded. PostgreSQL, Firefox/WebKit, Linux/Windows, full screen-reader review, and language-server restoration remain unavailable/blocked and are called out in the final report.
