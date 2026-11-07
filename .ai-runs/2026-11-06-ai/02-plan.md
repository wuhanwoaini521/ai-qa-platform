# AI 探索与回归修复改进

- run-date: 2026-11-06
- task-type: new-feature
- scale: standard

## Acceptance criteria

1. Eligible blocked exploration tasks expose a script-draft action only when the backend has a bounded history artifact and at least one successful replayable action.
2. The generated partial draft includes only successful actions and verified locators; partial output is visibly marked incomplete and remains user-reviewed/manual.
3. Goal verification remains false for incomplete tasks; the script model does not synthesize a page-title assertion for a partial draft.
4. Generated scripts without observed business-outcome assertions show a specific review warning.
5. Existing repair approval/apply/verify behavior is preserved, and verification UI says to use the created Run for actual scope.
6. Static validation passes; no tests are added or run in this task.

## Plan

- Extend the existing history artifact with redacted exploration status/evidence, and add a narrow `script_draft_available` bit to blocked step outputs.
- Let RecorderPage download that artifact on explicit user action; feed its archived/recent actions through the existing converter in a partial-draft-only mode.
- Add bilingual labels and warnings, and clarify repair verification scope copy.
- Run web typecheck/lint, focused Python lint/syntax and JSON validation, diff check; independently review the scoped changes. No E2E/pytest or live AI exploration will be run.
