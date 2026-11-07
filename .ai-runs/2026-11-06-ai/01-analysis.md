# AI 探索与回归修复改进

- run-date: 2026-11-06
- task-type: new-feature
- scale: standard

## Evidence and findings

- `TaskBrowserExecutor._browser_agent` persists `browser-action-history.json` for completed and blocked exploration runs, but a blocked task raises `TaskBlocked`; its failed step outputs contain the artifact id and stop reason rather than `browser_agent` success output.
- `RecorderPage` previously exposed script generation only for `COMPLETED` verified output, so safe successful history was inaccessible after an incomplete exploration.
- `recorderStepsFromAgent` already rejects unverified locators and maps observed page evidence to assertions. It previously allowed page-title fallback, which could be mistaken for goal coverage.
- Failure repair already has proposal/diff, human apply approval, deterministic verification run and rollback. No second repair runner is needed; improve scope disclosure only.
- Safety boundary: do not enable partial draft generation for approval, human verification, unsafe navigation, network/browser startup, or unstable-page stops. Only successful recorded actions with verified locators are reusable in partial drafts.

## Impact

- Backend: existing task/browser executor and artifact output only.
- Frontend: RecorderPage and its existing agent-to-recorder model; no new runtime or provider.
- Repair UX: existing WorkspaceRunResult translations.
- No API schema migration or runtime state migration.
