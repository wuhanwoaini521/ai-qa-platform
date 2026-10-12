# Implementation

- `apps/api/app/adapters/playwright/browser_runtime.py`: added a platform-aware standard Chrome User-Agent builder using the active browser version. Applied it only to headless browser contexts; headed sessions remain unchanged. This removes the `HeadlessChrome` UA token that caused the target edge to reset the navigation.
- `apps/api/tests/test_browser_runtime.py`: added a real Playwright-context test asserting headless sessions expose the standard Chrome brand/version rather than `HeadlessChrome`.
- No dependency, proxy, runtime-data, or user configuration changes.
