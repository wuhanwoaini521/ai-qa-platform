# Autonomous QA Agent V1

V1 composes the existing persisted Task Runtime and its registered tools. It does not add a second agent runtime, planner service, event stream, AI framework, or dependency.

## Goal and planning flow

`POST /api/tasks/preview` accepts a `QA_GOAL`, selected project/workspace, and scope IDs. The existing goal parser resolves the goal into a bounded contract; `build_qa_goal_plan` composes registered `TaskStep` tools from that contract and current requirement, case, automation, and failure facts. The preview returns readable step titles, conditional markers, risk, effects, constraints, and a `plan_token`.

`POST /api/tasks` recomputes the contract, facts, and plan. It rejects a missing or stale token, so a changed requirement, case, automation binding, scope, or goal must be previewed again before execution. The task stores the accepted contract and the exact request/context digest. Execution records its steps and events through the existing Task Runtime and SSE endpoint.

The UI presents the plan in Workspace. Workflow exposes the runtime DAG and events for inspection. A plan is a readable projection of the persisted runtime plan; there is no second task state.

## Capability map

| Capability | Input → output | Side effect and risk | Approval | Runtime/context/entry |
|---|---|---|---|---|
| Requirement analysis | Requirement ID → analysis and lifecycle evidence | Writes analysis metadata; low | No source approval | `requirement.analyze`; requirement-scoped Workspace goal |
| Coverage analysis | Requirement/case/project facts → uncovered cases and criteria | Read-only; low | No | `goal.coverage`; selected project context |
| Test design and case creation | Requirement analysis/scenarios → test designs and missing cases | Creates records; medium | Existing product policy | `goal.materialize_cases`; requirement ID and project |
| Automation generation | Requirement/cases and observed page evidence → generated test proposal | AI call and artifact; medium | Source application is separately gated | `tests.generate`; `QA_GOAL` or existing Create Test flow |
| Code review | Python source/tests → structural findings and evidence | Read-only; low; bounded AST review is not semantic proof | No | `source.inspect`, `source.review`, `goal.review_project`; selected workspace/file |
| Test execution | Node IDs or discovered tests → linked `TestRun` and executions | Starts pytest; medium | No general approval gate; preview labels execution risk | `tests.resolve`, `tests.run_*`; workspace and requested scope |
| Browser inspection | URL → title, accessibility evidence, candidates, screenshot | Read-only browser session; low | No | `browser.inspect`; URL/recorder context |
| Browser interaction | Observed candidate → one safe action and post-action observations | Changes browser state; medium/high by action classifier | Destructive or unclassified action is blocked pending user decision | `decision.select_candidate`, `browser.act`, `browser.verify`; observed candidates only |
| Recorder | Browser session events → persisted recording and context | Persists session/events; medium | Existing recorder policy | Existing Recorder service and WebSocket; not a new Goal-only runtime |
| Locator intelligence | Observed candidates and page context → selected locator and verification evidence | Read-only selection; low | Jev only for a real candidate choice; local strategy fallback | `LocatorDecisionService`; browser action flow |
| Failure classification | TestRun output → failure classes and linked records | Persists failure records; low | No | `failure.classify_run` / `FailureClassifier`; child Run |
| Failure diagnosis | Failure/source evidence → diagnosis and repairability | AI invocation when provider is available; read-only; low | No source write | `failure.diagnose`; Failure and workspace context |
| Repair proposal | Eligible failure → bounded diff proposal and artifact | Creates proposal artifact; medium | Yes, before application | `failure.prepare_repair` → `task.request_approval` |
| Apply repair | Approved proposal and unchanged source baseline → workspace change | Writes source; high | Explicit approval; baseline is rechecked | `source.apply_repair`; original task and file context |
| Retry/replan | Failed step or user guidance → bounded retry/replanned remaining steps | Re-executes selected work; medium | Existing approval still applies to writes | Existing Task Runtime retry/replan limits and task state |
| Verification/result | Run or browser evidence → result contract, trace links and unresolved items | Persists evidence and summary; low | No | `tests.verify`, `browser.verify`, `goal.summary`; Task/Run/Case/Failure/artifact IDs |
| Debugger | Debug session and selected runtime context → interactive inspection | May change a live debugging session; medium | Existing debugger controls | Existing Debug service; not currently composed as an autonomous Goal tool |

Risk is descriptive in plan previews and enforced by the existing browser/source approval paths; it is not a new permission framework.

## Constraints and safety

- `只分析，不要修改` and `不要运行测试` remove write/run steps from the accepted plan.
- `不要使用浏览器` removes browser-dependent steps; it does not silently create a browser session.
- Ambiguous project goals default to bounded read-only review. A test run requires explicit run language or an exact scoped run goal.
- Generated test source is checked for assertion bypass patterns before approval. Source changes are not applied without a persisted approval decision.
- Browser actions use observed candidates, semantic/visibility/occlusion checks, and the action risk classifier. Explicit page-text criteria must be observed before verification can pass.
- Goal start deduplicates the same client request key inside one API process, using recent persisted tasks. The current implementation does not provide a cross-process uniqueness guarantee. A preview token binds the current plan to the start request.

## Continuous execution, recovery, and resume

The persisted DAG runs safe sequential steps without asking the user to click between them. Retryable tools retry within step/task limits. Fatal or unavailable work is recorded as blocked or unresolved rather than reported as a pass. Failure diagnosis only enters repair when evidence classifies a failure as eligible; applying source changes still pauses for approval.

Approval state, decisions, artifacts, steps, and events are stored with the task. Refreshing the UI reconnects to the same task. Pause takes effect at a safe step boundary; a still-pending task pauses before starting. Resume uses a conditional `PAUSED → RESUMING` claim, reloads and syntax-checks changed Python files, recompiles the goal from current business facts, invalidates stale read/verification outputs (including generated drafts) and dependent summaries, then conditionally returns to `PENDING` or `WAITING`. The conditional claim prevents concurrent resumes from adding the same replanned steps twice; a cancel committed during replanning cannot be reverted to `PENDING`.

`max_duration_seconds` is an active execution budget shared across worker restarts, pauses, approvals, and replans. The runtime persists consumed worker time; waiting for a user decision does not consume the remaining budget. Child pytest runs receive the remaining task deadline rather than resetting the budget or inheriting the standalone-run timeout.

## Result contract

The final `goal.summary` records the goal, verdict, completed work, findings, changes, test counts, Run/Case/Failure/artifact links, unresolved items, constraints, AI provider/model/call/latency/fallback/error counts, and a recommended next action. A completed runtime task can still have `COMPLETED_WITH_UNRESOLVED`; the UI labels execution status and goal verdict separately. No Run is shown as “tests not run,” not as zero passing tests.

## Implementation references

- Goal parsing and plan composition: `apps/api/app/services/task_workflows.py`
- Persisted Task Runtime, approval, pause/resume, retry, verification, and result contract: `apps/api/app/services/task_runtime_service.py`
- Goal preview/start/pause/resume API: `apps/api/app/api/tasks.py`
- Existing Task model and state enums: `packages/project-model/project_model/task_models.py`
- Workspace goal UI: `apps/web/src/features/workspace/WorkspacePage.tsx`
- Runtime actions and Workflow view: `apps/web/src/features/runtime/RuntimeTaskActions.tsx`, `apps/web/src/features/workflow/WorkflowPage.tsx`
