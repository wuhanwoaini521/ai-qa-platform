# Round 17 re-audit (user task m07420)

Prompt: verify the delivered Versioned QA Workflow Studio against its own seven phases, using code and
re-runnable evidence — not the prose in the round report — then fix only what is really broken.

## What was already real

| Phase | Claim | Evidence found |
|---|---|---|
| 1 design (7 outputs) | boundary, versioning, node contracts, whitelist, DAG/cycle checks, definition↔run link, permissions | `docs/WORKFLOW_STUDIO.md` §1–§6; `workflow_definition.py:436-449` enforces a human-approval ancestor for every writing node |
| 2 versioned definition | draft / versions / compare / restore / publish / immutable | all seven routes exist (`apps/api/app/api/workflow_definitions.py`); draft conflicts use `base_checksum` → 409 |
| 3 React Flow editor | drag, add/remove, connect, inputs, save, auto-layout, fold, undo/redo, validation, version compare | `WorkflowEditorPanel.tsx`, `workflowEditorModel.ts` |
| 4 restricted execution | must run through TaskRuntimeService, no second scheduler | `compile_plan` exists at `workflow_definition_service.py:226` but **no route calls it** → B/C remain BLOCKED by design |
| 5 definition vs execution diff | matched / skipped / failed / undeclared, UNKNOWN where evidence is missing | `GET /api/workflows/{id}/execution-diff`; the response carries an explicit `unknown` list (`step_inputs_are_not_compared`, …) |
| 6 evidence + test-data governance | task-level evidence for new runs, isolated acceptance data | repair task `7a5e3a6f3462446183d245b6ccf56ad9` holds 9 `agent_task_evidence` rows over 11 steps |
| 7 acceptance | 12 numbered real-browser items | 20 checks existed; 4 items were only implicit |

## Real defect (P1, fixed)

`WorkflowEditorPanel.tsx` computed `dirty = !sameGraph(present, saved)` while `canonical()` drops
`position` on purpose (layout must not look like a graph edit), and the save button is
`disabled={!dirty}`. So dragging a card never enabled 保存草稿 — the arrangement could not be persisted at
all, and Phase 3's "节点拖拽" plus Phase 7's "刷新后草稿正确恢复" were both untrue for layout.

Fix: `sameLayout()` in `workflowEditorModel.ts` (sorted, rounded coordinates) and
`dirty = !sameGraph(...) || !sameLayout(...)`. Graph meaning, checksums and version diffs are untouched;
publishing still requires a saved draft.

## Checks added (20 → 24, all PASS)

1. a cyclic draft is refused at publish, not merely flagged → `422` + "form a cycle".
2. a workflow that would write without a human approval step cannot be published → `WRITE_WITHOUT_APPROVAL`, `422`.
3. restoring version 1 gives a draft with that graph and leaves the published version alone.
4. a dragged card stays where it was put after a reload (`save_enabled_after_drag: true`, moved key `run`).

## Test-data governance

`DiscoveryIntelligenceService._create_case` now stamps `suggestion:<suggestion_id>` next to
`discovery`/`ai-suggestion`/`candidate-gap`, so acceptance-created cases have exact provenance. Cleanup
stays id-scoped (`docs/WORKFLOW_STUDIO.md` §11); coverage keeps counting approved cases because a human
approved them.

## Verdicts

- A 工作流定义与编辑：**PASS**（24/24 真实验收，缺陷已修）
- B 工作流执行：**BLOCKED**（`compile_plan` 存在但无执行路由；未自建第二套调度器）
- C 任意 DAG 编排：**BLOCKED**（同上）
