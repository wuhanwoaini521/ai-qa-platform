# Plan

1. Run the Ponytail audit against README, build/deploy/dependency configuration, API/web/worker entrypoints, route table, relevant tests, and critical browser/repair flows; record concrete findings, preserved boundaries, and before/after metrics in `ponytail-audit.md`.
2. Fix BrowserRuntime resource ownership: expire idle sessions without requiring a later API request, provide `close_all()` for API shutdown, and guarantee cleanup if browser-context setup fails. Add focused tests for idle expiry, shutdown closure, and setup failure.
3. Fix recurrence history failure handling in `FailuresPage`: distinguish loading/empty/error, provide retry, and ignore stale responses when a different failure is selected. Also remove only its proven-dead standalone failure-queue mode: `/failures` redirects to Workspace and the sole component caller always uses Workspace mode. Verify visible error→retry recovery in the real browser.
4. Remove only the worker image's redundant unpinned Playwright install; retain `playwright==1.62.0` and install its browser binaries from the locked environment.
5. Run targeted runtime/frontend tests first; then full backend/web tests, lint/format, typecheck, OpenAPI/i18n checks, and production web build. Docker is unavailable locally, so validate the worker image instructions and resolved Playwright version without claiming a container build.
6. Switch to challenge-review, retry the Orca independent review if available, check only the staged scoped diff, then commit source and this subdirectory's report/evidence separately. Do not stage inherited Round 1/API/generated-contract/`mise.toml` changes.

## Acceptance criteria

- An idle browser session is closed by TTL without a subsequent request; all remaining sessions close on API shutdown; a setup/close error does not leak Playwright or replace the original failure.
- A recurrence API error is shown as an error, not an empty result; a retry can recover and an older request cannot overwrite a newer selection.
- Worker dependency resolution remains Playwright 1.62.0; worker Dockerfile no longer overwrites it with an unpinned pip install.
- No route, public API, test, runtime/provider, approval boundary, or unrelated dirty file is removed or changed.
- All executed checks/results and the exact acceptance limits are recorded. Any unavailable reviewer/container/platform gate remains PARTIAL.
