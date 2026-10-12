# Functional Testing

## Automated

- `pnpm --filter @ai-qa/web test` — PASS, 105/105.
- `pnpm --filter @ai-qa/web lint` — PASS.
- `pnpm --filter @ai-qa/web build` — PASS (`tsc -b` and Vite production build). Existing non-blocking Monaco editor chunk warning (>4 MB) remains.
- `git diff --check` — PASS.

## Real browser

- System Chrome, actual Workspace result route and existing real run (no demo data or new run).
- Desktop: inspected normal state and independently scrolled the middle repair panel using a native wheel event. The repair panel title stayed pinned; the partially clipped blocker no longer showed above it. Evidence: `/tmp/aiqa-result-sticky-scrolled-final.png`.
- Long event title wraps within the event row and leaves its `PASSED` badge visible. Evidence: `/tmp/aiqa-result-layout-desktop-final.png`.
- Narrow mobile (Chrome window 420 px wide): result panels stack and the page showed no page-level horizontal overflow. Evidence: `/tmp/aiqa-result-layout-mobile.png`.
- Tablet (Chrome window 990 px wide): resized the already-loaded real run without reloading; panels remained within the viewport and long event titles wrapped without covering status badges. Evidence: `/tmp/aiqa-result-layout-tablet-loaded.png`.

A fresh tablet-sized reload once showed the no-run empty state despite retaining the run ID in the URL; resizing the loaded desktop result to tablet displayed the run correctly. This appears separate from the CSS changes and was not modified. An attempted DevTools console injection was abandoned after keyboard-generated punctuation caused syntax errors; DevTools was closed and the app reloaded before the successful native-scroll check. No app data was written.
