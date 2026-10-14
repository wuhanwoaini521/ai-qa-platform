# Fixes applied

1. **Browser ownership:** Added one runtime-owned idle reaper, explicit `close_all()` on the existing port/adapter, and API shutdown cleanup. Setup cleanup now attempts both browser and Playwright teardown without replacing the original setup exception.
2. **Recurrence requests:** API failures show a translated retryable error instead of a false empty history. Request ids suppress stale success/error/loading updates. Browser verification covered abort → retry success and a delayed stale response.
3. **Dead UI:** Removed only the unreachable standalone failure queue/header branch and its unused props, callback, CSS, and locale labels. The `/failures` compatibility redirect and embedded failure detail remain.
4. **Worker image:** Removed the redundant unpinned `pip install playwright`; retained installation of Chromium and Firefox with the already-resolved Playwright 1.62.0 executable.

No AI/Jev action, repair Apply, external write, schema/REST change, page/route/provider/runtime removal, or dependency upgrade occurred.