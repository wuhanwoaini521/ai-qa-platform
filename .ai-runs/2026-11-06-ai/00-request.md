# AI 探索与回归修复改进

- run-date: 2026-11-06
- task-type: new-feature
- scale: standard
## Original Request

Improve the product's AI capabilities: natural-language browser exploration that produces scripts, AI-assisted regression repair, and other high-value testing pain points.

## Resolved Scope

- Allow safe, successful actions from eligible blocked `EXPLORE_PAGE` tasks to produce an explicitly incomplete draft from the existing browser-history artifact.
- Keep strict locator verification, never label a partial exploration as goal-verified, and require user review/manual run.
- Warn when generated scripts lack an observed business-outcome assertion; do not treat a page-title assertion as business proof.
- Clarify that repair verification is targeted and the created Run is the source of truth for its actual scope. Reuse existing human-approved repair workflow.

## Repository / Branch / Initial Git Status

- `D:\code\self-github\ai-qa-platform`, branch `main`, HEAD `512b473`.
- Initial tree was already dirty with recorder, workspace UI and handoff edits, plus pre-existing `.ai-runs/` directories. Those changes are preserved and are not attributed to this task.
