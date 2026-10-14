# Ponytail audit — Round 4 codebase cleanup

## Scope and disposition

Audited API/web/worker entrypoints, BrowserRuntime ownership, app shutdown, failure recurrence states, route and component callers, Docker dependency resolution, provider/runtime boundaries, and repository test/build configuration. Only the independently evidenced defects in `03-findings.md` were changed.

| Area | Before | After | Disposition |
|---|---|---|---|
| Browser idle TTL | Access-time expiry only; no reaper (`1` lazy check, `0` reapers) | Same access check plus `1` runtime-owned reaper | Fixed and covered by an autonomous-expiry test |
| Runtime shutdown | `0` BrowserRuntime `close_all()` methods and `0` lifespan calls | `1` port/adapter method and `1` lifespan shutdown call | Fixed; existing Runtime/adapter reused |
| Browser setup cleanup | Browser-close failure could skip Playwright cleanup and mask setup error (`1` path) | Both cleanup attempts are made; original error is re-raised with cleanup notes | Fixed and covered with fakes |
| Worker Playwright install | `1` redundant unpinned `pip install playwright`; locked package resolved to 1.62.0 | `0` unpinned package installs; locked version remains 1.62.0 | Fixed; browser-binary installation retained |
| Recurrence errors | `1` catch path turned failures into empty results; `0` error/retry UI; `0` stale guard | `0` false-empty catch paths; `1` translated retry state; `1` request-id guard | Fixed; browser-tested failure, retry, and stale response |
| Standalone failure queue | `1` unreachable branch; route redirects and sole caller uses embedded mode | `0` standalone branches; `/failures` redirect and embedded detail remain | Removed only the dead branch, props, styling, and strings |
| Other cleanup candidates | Artifact-client aliases, compatibility routes, runtime types, provider registries, and separate runtime owners have real callers/boundaries | Retained | No evidence justified deleting or merging them |

The standalone queue removal deleted **133 lines** in `FailuresPage.tsx`; the source commit also adds the recurrence error/retry behavior and removes its dead supporting styles/props/strings. No REST route/schema, public client method, page, dependency, runtime, or provider was removed. The existing BrowserRuntime port gained only the internal `close_all()` lifecycle capability.

## Guardrails

- No AI/Jev action, Apply, source write, or external write was performed.
- Human approval remains the only source-write path; AI does not decide PASS/FAIL.
- No dependency upgrade or unrelated worktree cleanup was done. `mise.toml` and inherited edits remain untouched.

## Validation metrics

- Python: 755 passed, 8 skipped; 0 failed.
- Web: 147 passed; typecheck, lint, and production build passed.
- Python Ruff check/format and i18n parity passed.
- Resolved Playwright version: 1.62.0 before and after.
- Worker image build, basedpyright, PostgreSQL concurrency, cross-platform CI, axe/cross-browser, and live AI/Jev acceptance remain unavailable or unrun as documented in `04-functional-test.md` and `09-final-report.md`.
