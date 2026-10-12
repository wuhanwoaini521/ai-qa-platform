# Plan

1. Add a small platform-aware Chrome User-Agent builder to the existing Playwright adapter and apply it only to headless contexts.
2. Add an adapter-level test that checks the actual headless page User-Agent does not expose `HeadlessChrome` and matches the runtime browser version.
3. Run the browser-runtime tests, then verify the target Uniqlo URL through the actual project runtime in headless mode and perform focused regression/review.
4. Preserve all unrelated working-tree changes and record limitations and final acceptance.

## Acceptance

- The project headless browser navigates the target URL and receives a successful HTTP response.
- Existing browser-runtime behavior and tests remain passing.
- Headed sessions and non-browser code/configuration are unchanged.
