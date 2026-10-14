# Repository analysis

## Prior-round work reviewed

- Round 1 reports describe API analysis tasks decoupled from SSE, persisted cancel/timeout/recovery, and proposal-only AI/Jev acceptance. That source diff remains inherited and uncommitted; the report explicitly says it was not committed because it overlapped later work. Do not restage it as Round 4.
- Round 2 commits `a78fdf1` and `ede45cb` share RuntimeDetail loading/error and authenticated blob transport, and compose Task Runtime/Discovery dependencies through `app.container`. Its architecture report confirms there is one BrowserRuntime port/Playwright adapter, separate TestRun/Task/Discovery/Debug lifecycles, and distinct AI vs decision-provider registries. Keep those boundaries.
- Round 3 commits `c05c939`, `8e2d4a2`, and `0ac703c` cover keyboard-scrolling the failure timeline and Studio/workbench run target/config, responsive navigation, timestamp, debugger toolbar, and browser evidence. Its acceptance remains PARTIAL because Orca review was unavailable.
- Existing Round 4 commit `652736b` makes locator proposal rejection persistent and keeps human Apply as the only source-write path. Round 5 report records 752 Python passes (8 skipped), 146 web passes, and a PARTIAL overall gate; do not repeat rejection work or claim blocked gates complete.

## Architecture and protected state

- Web HTTP is centralized in `apps/web/src/api/client.ts`; recorder/debugger/LSP WebSockets are feature protocols, not alternate REST clients.
- API composition is in `apps/api/app/container.py`; `main.py` owns lifespan. `BrowserRuntime` has one production adapter, while recorder, task, discovery, and failure workflows own their specific sessions.
- `AppRoutes` contains live/lazy routes and compatibility redirects. `RecorderPage` is dynamically imported by `WorkspacePage`; requirement/test-case pages are also consumed there. `/failures` is a compatibility redirect into Workspace; the only `FailuresPage` caller uses the embedded Workspace mode, so its standalone queue branch—not the route or page—is provably unreachable.
- Runtime DTOs in `apps/web/src/types/runtime.ts` overlap generated OpenAPI shapes, but generated fields are optional while the server's serialized projection provides defaults and current UI consumers require them. Keep the handwritten projection until a type-safe contract migration is proven.
- The `api.getArtifactBlob` and `api.downloadArtifact` methods are two names for the same endpoint; both have real callers. Keep them for compatibility rather than remove a public client method. The BrowserRuntime port/adapter, LiveBrowserPanel, and Runtime UI are separate layers, not duplicate runtimes.
- Initial worktree contains inherited Round 1 failure-lifecycle/API/client/config/docs/generated-contract changes plus `mise.toml` and other uncommitted work. Leave all unrelated paths/index entries untouched.

## Confirmed issues

1. `PlaywrightBrowserRuntime.get_session` enforces idle TTL only when that same session is accessed. The recorder WebSocket stops polling after disconnect and its owner retains the session; no sweeper runs, so an abandoned Chromium process can remain open until another access or API shutdown. Main lifespan closes recorder/debug/task-owned resources but has no final `BrowserRuntime.close_all` fallback.
2. `apps/worker/Dockerfile` runs an unpinned `pip install playwright` after `uv sync --frozen --no-dev --package worker`, overwriting the workspace's explicit `playwright==1.62.0` dependency with whatever pip resolves. This conflicts with the repository's required Playwright version. `playwright install` can use the already-installed pinned executable; the extra package install is redundant and unsafe.
3. `FailuresPage.fetchRecurrence` catches API errors, clears the list, and renders the same empty-state message as a successful zero-result response. A 5xx/network failure therefore falsely looks like “no similar history” and offers no retry.
4. A browser/context setup failure path calls `browser.close()` before `_stop_if_idle()`. If close itself raises, the original failure is masked and Playwright cleanup is skipped.

## Scope / risk

HIGH risk overall; selected changes are limited to BrowserRuntime lifecycle, a failure-page recurrence request state, and the worker image's Playwright install command. No persisted schema/API change, external provider call, test verdict change, repair Apply, dependency upgrade, or runtime-data cleanup is needed. No candidate for deleting pages, providers, routes, tests, or dependencies has enough evidence.

## Tooling note

The project-delivery instructions reference `scripts/init_run_log.py`, but that file is absent in this repository. This scoped record was created manually under the requested existing Round 4 directory; no generator was added.
