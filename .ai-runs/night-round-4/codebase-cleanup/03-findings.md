# Findings and selection

## Selected (verified in source and connected callers)

| Priority | Finding | Evidence | Smallest sufficient fix |
|---|---|---|---|
| P1 | Browser session idle TTL is lazy, not a cleanup guarantee; app shutdown also omits a BrowserRuntime final close. An abandoned recorder session can keep browser resources alive. | `PlaywrightBrowserRuntime.get_session()` checks TTL only on access; recorder stream exits on disconnect without closing the reusable recording session; API lifespan only closes recorder/debug/task owners. | One runtime-owned periodic idle reaper, idempotent `close_all()` in the existing protocol/adapter, and invoke it from lifespan shutdown. Cover expiry/close-all. |
| P1 | Setup failure can skip Playwright teardown and mask the original context/page error if `browser.close()` raises. | `create_session()`'s context-setup `except` awaits browser close before `_stop_if_idle()` and re-raises only after both. | Attempt both cleanup operations, attach cleanup failures as exception notes, then re-raise the setup error. Test with fakes. |
| P2 | Worker image can silently upgrade Playwright past the required exact version. | Worker `uv sync --frozen` resolves `playwright==1.62.0`, then a separate unpinned `pip install playwright` overwrites it. | Remove only redundant package install; retain `playwright install --with-deps chromium` using the locked venv's CLI. |
| P2 | Recurrence API failure is indistinguishable from a valid empty response and has no retry. | `fetchRecurrence` catches, logs, and sets `[]`; page renders `recurrenceEmpty` for all zero-length lists. | Track request error separately, clear stale results, render a translated error/retry state, and guard overlapping requests. |
| P2 | `FailuresPage`'s standalone failure queue/header branch and related CSS/locale strings are unreachable. | `/failures` is a compatibility redirect to Workspace; the only `FailuresPage` caller passes embedded Workspace mode. | Remove the unused mode/list UI and dead styling/strings; preserve the route and embedded failure-detail workflow. |

## Audited but retained

- No page/route removal: Recorder is both a route and an embedded lazy import; Workspace links to Requirements/Test Cases. Only the proven-unreachable standalone branch inside `FailuresPage` was removed; the page, redirect, and embedded failure details remain.
- No client method removal: both artifact download/blob methods have consumers and share authenticated transport; compatibility is intentional.
- No runtime/provider consolidation: one BrowserRuntime adapter/port, while recorder/debug/task/discovery manage different ownership and lifetimes; AI and deterministic decision registries are intentionally separate.
- No handwritten runtime-type deletion: server defaults and required UI projection are stronger than generated optional fields.
- No dependency deletion: this audit found no dependency proven unused. Worker Playwright is required; only its duplicate unpinned install is removed.
- No source mutation changes: rejection still persists, AI never determines PASS/FAIL, external writes remain preview/approval gated, and source repair still requires explicit Apply.

## Baseline metrics (before implementation)

- BrowserRuntime: idle TTL check present = 1; periodic reaper = 0; `close_all` API = 0; lifespan BrowserRuntime shutdown call = 0.
- Worker image: unpinned `pip install playwright` occurrence = 1; workspace package pin = `playwright==1.62.0`.
- Failure recurrence: API request catch collapses error to empty list = 1; dedicated error/retry UI = 0; stale-request guard = 0.
- Proven dead standalone `FailuresPage` mode = 1 before implementation; route/page/client method/provider/dependency deletions planned = 0; dependencies removed = 0; public API/schema changes planned = 0.

## Risks / validation

Browser cleanup changes an async shared singleton and will be tested with deterministic fakes plus existing Playwright integration tests. The UI change is stateful and will be checked through a real browser with the recurrence endpoint forced to fail once, then allowed to recover. Docker is not installed in this environment; the image build will remain explicitly unverified even if Dockerfile and lockfile checks pass.
