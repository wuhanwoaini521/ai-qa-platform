# Task Routing

Use one primary workflow from the six task types below. A task can match more than one type: first identify all relevant concerns, then choose the workflow that covers the highest **actual** risk. Do not rank types mechanically. Consider behavior impact, architecture impact, data/security impact, user-facing impact, and regression surface. Add distinct mandatory gates from other matched types (for example, a bug fix that changes UI behavior also gets UI review).

## Six task types

| Type | Choose when | Core route | Additional gate |
| --- | --- | --- | --- |
| `bug-fix` | Restore behavior that should already work. | Evidence → reproduce/validate root cause → fix → targeted test → review → regression → acceptance | UI review if user-facing UI changes. |
| `new-feature` | Add a capability that did not exist. | Requirements → architecture/impact → plan → implement → functional test → review → regression → acceptance | UI review for new UI or interaction. |
| `ui-feature` | Add or change a page, component, or interaction while retaining the overall visual direction. | UI context → implement → functional test → browser review → fix → review again → regression → acceptance | Real browser and responsive checks when available. |
| `ui-redesign` | Rework the visual structure or interaction model of an existing UI. | UI audit → design direction → implementation → functional test → independent UI review → fixes/re-review → code review → regression → acceptance | Use a representative sample first when the surface is broad. |
| `refactor` | Change internal structure without intending to change external behavior. | Understand behavior → safety tests → refactor → regression → review → acceptance | Behavior preservation is the acceptance constraint. |
| `maintenance` | Change dependencies, configuration, tooling, CI, or operational workflows. | Inspect current use → plan → change → compatibility/validation → review → regression → acceptance | Check compatibility and existing automation. |

If the task is a mix, keep one primary type for the run log but retain all applicable checks. A small UI bug fix can remain `bug-fix` plus UI review; a broad redesign with behavior changes can use `ui-redesign` plus relevant bug/feature tests. A UI label alone does not make a task higher risk than persistence or authentication work.

## Risk level

Risk is separate from task type. Record it in analysis and let it determine planning detail, test depth, review depth, and regression scope. **Every actual code change still requires verification.**

- **LOW** — local copy change, narrow style adjustment, or leaf refactor with no behavior change and few consumers. Use focused checks and review the complete diff.
- **MEDIUM** — page interaction, API integration, component behavior, or service logic. Test success and failure paths and relevant callers.
- **HIGH** — cross-module behavior, authentication/authorization, persistence, execution engines, workflow orchestration, migration-like changes, or widespread refactoring. Analyze dependencies and failure modes in depth; broaden integration, regression, and review coverage.

When evidence changes the risk estimate, update the plan and record the reason. Do not use risk as a reason to skip testing.

## Outside this skill's scope

Pure explanation, advice, architecture discussion, repository-health audit, file-only review, and testing an application without changing it are not delivery tasks. Release management and architecture governance are separate responsibilities. A concrete code change involving these areas can still route through the relevant task type. Do not assume specialist skills exist; use them only when available and appropriate.
