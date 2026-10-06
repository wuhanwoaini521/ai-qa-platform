---
name: project-delivery
description: "Coordinate end-to-end software changes through verification, independent review, regression, and acceptance. Use to implement or build features, add functionality, upgrade existing features, fix bugs, modify or improve modules, clean up implementations, repair workflows, refactor code, implement approved UI/design specifications, maintain or upgrade projects, or improve applications end to end; Chinese requests include 开发功能、修 bug、改造模块、按设计方案实施页面改动、重构项目、完善流程. Exclude code or error explanations, repository summaries, file-only reviews, advice-only or plan-only requests, architecture questions, library comparisons, technical Q&A, read-only audits, release management, and full-application testing without changes; exclude UX-led usability audits, workflow or information-architecture reviews, and experience-led redesigns, which use ui-ux-review for UX analysis and compose with this skill for implementation delivery; 只分析、只审查、只给计划 are also excluded. Read-only work must not create `.ai-runs` files."
---

# Project Delivery

Coordinate repository changes from a concrete requirement through verified acceptance. This is a **software modification and delivery orchestrator**: it is not a code explanation, error interpretation, repository audit, release-management, or architecture-governance skill.

Implicitly use this skill when the user asks for an implementation, repair, refactor, UI change, maintenance change, or end-to-end improvement. Do not start it for a request that only asks for explanation, suggestions, review, health assessment, or whole-project testing without changes. If the user explicitly invokes this skill but asks for read-only work, use the read-only contract below.

## Read-only contract

For `analyze only`, `review only`, `inspect only`, `do not modify`, `no file changes`, or `only give me a plan` requests, inspect and report only. Do not create `.ai-runs/`, call `scripts/init_run_log.py`, write a plan file, or modify source, tests, docs, or config. This applies even when the skill was explicitly invoked. A read-only plan belongs in the response, not in the repository.

## Delivery workflow

```text
Requirement → Repository Understanding → Impact Analysis → Plan
→ Implementation → Targeted Verification → Independent Review
→ Fix Findings → Regression → Acceptance
```

Before editing, pass the Repository Understanding Gate: read repository guidance; map the project structure; locate and read the relevant implementation, callers, tests, configuration, and architecture; assess behavior, data, user-facing, and regression impact. Extend existing implementation where possible; do not create files before checking for an existing home.

Classify the task using the six routes in `references/task-routing.md` and assign `LOW`, `MEDIUM`, or `HIGH` risk. For mixed tasks, weigh behavior, architecture, data, user-facing impact, and regression surface; do not apply a fixed type ranking. Add every applicable gate, including UI review when user-facing UI changes.

Make the **smallest coherent solution**, not merely the smallest patch: reuse existing modules and abstractions, follow repository conventions, preserve required compatibility, and avoid duplicate services/pages/hooks/components, speculative wrappers, unrelated refactors, and scope expansion. For bugs, establish evidence and validate the root cause before fixing; follow `references/development.md`.

For every code change, verify real behavior. Start with the most relevant targeted checks, then add integration checks and risk-appropriate regression. Do not substitute static inspection for runnable behavior when actual execution is available. Follow `references/functional-testing.md` and `references/regression.md`.

Independent code review is mandatory. Review correctness, edge cases, architecture fit, duplication, failure handling, security, maintainability, and test gaps. Use a separate reviewer when available and authorized; otherwise perform a structured second pass over the diff. Fix blocking findings and re-run affected checks. UI changes also require the real-browser gate in `references/ui-review.md` when browser capability exists; if unavailable, report `Browser verification: NOT AVAILABLE` and do not claim a pass when real UI behavior remains unverified.

## Gates and acceptance

- Every actual code change has relevant verification; risk changes depth, never whether to verify.
- `P0` findings block acceptance. An unresolved correctness, safety, compatibility, regression, or security `P1` also blocks `PASS`. Scope-external or non-blocking improvements may remain only when documented with a disposition.
- Regression scope must match risk and affected callers. `HIGH` risk calls for broader regression.
- For an authorized delivery task, create run logs only after confirming it is a modification workflow. Record actions and results only after they occur; never prefill future outcomes. Read `references/execution-log.md`.
- Final verdict must be exactly `PASS`, `PARTIAL`, or `FAIL`, using `references/final-acceptance.md`.

## References

- `references/task-routing.md` — six task types, mixed-task routing, and risk levels.
- `references/workflow.md` — repository gate and delivery-stage details.
- `references/requirements-analysis.md` — scope, impact, and testable acceptance criteria.
- `references/development.md` — implementation discipline and root-cause policy.
- `references/functional-testing.md` — targeted and functional verification.
- `references/code-review.md` — independent review and finding severity.
- `references/ui-review.md` — browser-based UI verification when applicable.
- `references/regression.md` — risk-based regression scope.
- `references/final-acceptance.md` — verdict criteria.
- `references/execution-log.md` — authorized `.ai-runs/` records.

When dedicated `full-project-validation` or `ui-ux-review` skills become available, they may handle their specialist work; this skill remains responsible for the overall delivery gates. Do not assume those skills exist or require them.
