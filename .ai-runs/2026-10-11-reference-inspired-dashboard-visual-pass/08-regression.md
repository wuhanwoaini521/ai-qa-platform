# Regression

- `pnpm --filter @ai-qa/web lint` — passed.
- `pnpm --filter @ai-qa/web test` — 113 passed, 0 failed.
- `pnpm --filter @ai-qa/web build` — passed.
- `git diff --check` — passed.
- Build retains the existing Monaco chunk-size warning; no dependency or lockfile changes were made.
- Browser smoke found no page errors or horizontal overflow at the reviewed viewports.
