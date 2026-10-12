# Regression Summary

## Covered boundaries

- Shared API-process BrowserRuntime ownership remains unchanged; no parallel browser, MCP, or provider path was introduced.
- Existing task planner, decision service, recorder session, and event persistence remain the path for browser-agent actions.
- Safety checks reject stale page/target state before dispatch; retries remain bounded and stale actions do not consume the browser-action budget.
- Failure recovery, unresolved outcomes, evidence links, event allowlisting, archive bounds/retrieval, and script replay have deterministic regression tests.
- Fast strategy retains AI candidate planning and skips optional Jev; effective platform policy can still require Jev.
- Real provider acceptance verified persistence and identical correlation IDs across AI, Jev, decision/action events, and browser action records.
- Existing API and QA-core regression suite passed: **683 passed, 8 skipped**.
- Frontend suite passed (**138 tests**), as did typecheck, production build, Python/ESLint/i18n lint, and diff whitespace checks.

## Remaining risks and boundaries

- The browser task flow is live-verified through the task/browser execution service with real AI and Jev; the Recorder UI button itself was not used to submit that live task.
- No independent external reviewer was available; only a structured in-session second pass was completed.
- The full suite emits collection/fixture/SQLAlchemy warnings, and Vite reports a large Monaco/editor chunk. These did not fail verification and were not changed in this task.
- Standard pytest worker and Debugger browser sessions remain separately owned as before; this change does not unify those process boundaries.
- `.ai-runs/` is not ignored in the observed repository status. Run logs remain untracked; no `.gitignore` change or staging action was made.
