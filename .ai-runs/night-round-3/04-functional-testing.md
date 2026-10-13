# Functional testing — night round 3

- `rtk pnpm --filter @ai-qa/web test`: **PASS**, 146 tests.
- First RTK typecheck invocation misparsed pnpm's package filter and reported `Command "tsc" not found`; this was a wrapper-routing failure, not a source diagnostic. Reran the package command directly: `pnpm --filter @ai-qa/web typecheck` — **PASS**.
- `rtk pnpm --filter @ai-qa/web lint`: **PASS**.
- `rtk pnpm --filter @ai-qa/web build`: **PASS**. Existing Monaco chunk-size advisory remains.
- `git diff --check -- apps/web/src/features/failures/FailureOverview.tsx`: **PASS**.
- Browser interaction: at 360px, the ordered list is focusable (`tabIndex=0`); with focus, ArrowRight moved horizontal scroll from 0 to 40px. Computed focus outline is visible. Live metrics saved in `evidence/keyboard-after-mobile-360.json`.
- API endpoints used only for read-only page data; no diagnosis, apply, rerun, or external write was triggered.
