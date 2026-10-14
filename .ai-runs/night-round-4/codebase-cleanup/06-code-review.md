# Code review (serial second pass)

## Challenge prompt

**Find concrete reasons this implementation should not be accepted yet.** Re-read the staged diff against the connected BrowserRuntime callers, the workspace route/caller, recurrence rendering, tests, Dockerfile, and approval boundaries.

## Review result

No unresolved correctness, safety, compatibility, or regression blocker was found in the scoped diff.

- **Lifecycle and concurrency:** One expiry task belongs to the existing `PlaywrightBrowserRuntime` singleton. It checks idle sessions on a bounded interval; explicit session access still checks TTL. `close_all()` clears and closes all owned contexts/browsers, stops the existing Playwright instance, and cancels the reaper. Shutdown callbacks run in an order that stops task/recorder/debug owners before the BrowserRuntime fallback. Fake-based tests cover autonomous expiry, all-session shutdown, and setup cleanup.
- **Failure handling:** Setup errors remain the raised error when browser or Playwright cleanup also fails; cleanup failures are attached as notes. Existing session-close behavior remains best-effort, and lifespan's `AsyncExitStack` still runs remaining shutdown callbacks if one fails.
- **UI behavior:** The request id prevents old success, error, and `finally` updates from replacing a newer selection. The browser race test exercised the stale-result case. Retry errors and successful empty data have distinct translated states.
- **Compatibility and safety:** The only interface change is the existing BrowserRuntime port gaining `close_all()`, implemented by its production adapter and checked by the full Python suite. No REST route, response schema, test verdict, provider, route, dependency pin, source-write path, or human-approval boundary was changed. `/failures` and embedded failure details remain.
- **Lean scope:** The dead standalone queue branch, its now-unused props/callbacks/styles/locale strings, and the redundant worker pip install were removed. No dependency, public API method, page, route, provider, or runtime was deleted.
- **Expected load:** The API process owns one runtime and one timer; each sweep is linear in that process's active browser sessions and runs at most every 30 seconds. This is bounded and consistent with session cleanup, not a per-request background loop.

## Independent-review status

This is an implementer second pass, **not** an independent review. The Orca CLI could not start; see `08-independent-review.md`. Independent approval remains unavailable, so this review cannot satisfy that gate.
